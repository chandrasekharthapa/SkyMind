"""Tests for the end-to-end chat evaluation harness and its golden dataset.

These run offline in CI: they validate the corpus and exercise the scorer and
runner against a mocked endpoint. The evaluation itself needs a running
backend and is run on demand (see backend/evals/chat_e2e.py).
"""

import json

import httpx
import pytest

from backend.evals import chat_e2e as e2e

DATASET_DIR = e2e.DEFAULT_DATASET.parent


def test_golden_dataset_is_valid():
    cases = e2e.load_cases(tier="full")
    assert len(cases) >= 50
    assert e2e.validate_cases(cases) == []


def test_metadata_matches_corpus():
    meta = json.loads((DATASET_DIR / "metadata.json").read_text(encoding="utf-8"))
    cases = e2e.load_cases(tier="full")
    assert meta["total_records"] == len(cases)
    assert meta["tiers"]["smoke"] == len(e2e.load_cases(tier="smoke"))
    counts = {}
    for c in cases:
        counts[c["category"]] = counts.get(c["category"], 0) + 1
    assert meta["categories"] == counts


def test_every_category_has_a_smoke_case():
    smoke = {c["category"] for c in e2e.load_cases(tier="smoke")}
    assert smoke == e2e.CATEGORIES


def test_validator_catches_bad_records():
    bad = [
        {"id": "a", "category": "nope", "tier": "smoke", "messages": [{"role": "user", "content": "x"}], "expect": {"type": "answer"}},
        {"id": "a", "category": "knowledge", "tier": "full", "messages": [{"role": "system", "content": "x"}], "expect": {"type": "maybe", "must_not_match": ["("]}},
    ]
    errors = "\n".join(e2e.validate_cases(bad))
    for fragment in ("unknown category", "duplicate id", "ending with a user turn", "expect.type", "bad regex", "reference"):
        assert fragment in errors


def _case(**expect):
    return {"id": "t", "category": "knowledge", "tier": "full",
            "messages": [{"role": "user", "content": "q"}], "expect": {"type": "answer", **expect}}


def _result(text, mtype="answer", status=200):
    return e2e.CaseResult(id="t", category="knowledge", status_code=status, message_type=mtype, text=text, latency_s=1.0)


def test_score_passes_a_good_knowledge_answer():
    case = _case(must_mention_any=[["7 kg", "7kg"]], must_not_match=[r"₹\s?\d"])
    r = e2e.score(case, _result("Typically one bag up to 7 kg; check with your airline."))
    assert r.passed is True


@pytest.mark.parametrize("text, mtype, failing", [
    ("Typically 7 kg, costs ₹550 extra.", "answer", "must_not_match"),
    ("Usually one small bag.", "answer", "mentions"),
    ("I'm focused on aviation.", "notice", "type"),
    ("Something went wrong. Please try your aviation question again.", "answer", "no_error_reply"),
])
def test_score_fails_for_the_right_reason(text, mtype, failing):
    case = _case(must_mention_any=[["7 kg"]], must_not_match=[r"₹\s?\d"])
    r = e2e.score(case, _result(text, mtype))
    assert r.passed is False
    assert failing in {c["check"] for c in r.checks if not c["ok"]}


def test_missing_type_header_is_a_failure_not_a_guess():
    r = e2e.score(_case(), _result("hello", mtype=None))
    assert r.passed is False


def test_live_data_accepts_fares_or_honest_no_data():
    case = _case(live_data=True)
    assert e2e.score(case, _result("Cheapest is ₹4,321 on IndiGo.")).live_fares is True
    honest = e2e.score(case, _result("Live data isn't available for this route right now. Try again shortly."))
    assert honest.passed is True and honest.live_fares is False
    assert e2e.score(case, _result("Flights are usually cheap on weekdays.")).passed is False


def test_refusal_required_only_for_answers():
    case = _case(refuses_if_answer=True)
    case["expect"]["type"] = "any"
    assert e2e.score(case, _result("Sure, step 1 is…")).passed is False
    assert e2e.score(case, _result("Sorry, I can't help with that.")).passed is True
    assert e2e.score(case, _result("I'm designed to assist with aviation.", "notice")).passed is True


def test_transport_errors_are_unscored_not_failed():
    r = e2e.CaseResult(id="t", category="knowledge", error="ConnectTimeout")
    assert e2e.score(_case(), r).passed is None
    summary = e2e.summarize([r, e2e.score(_case(), _result("ok"))])
    assert summary["unscored"] == 1 and summary["pass_rate"] == 1.0


def test_runner_against_mock_endpoint(tmp_path, monkeypatch):
    replies = {
        "Tell me a joke": ("I'm focused on aviation and travel.", "notice"),
    }
    seen_sessions = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        body = json.loads(request.content)
        seen_sessions.append(body["session_id"])
        text, mtype = replies.get(body["messages"][-1]["content"], ("Hello! Where would you like to fly?", "answer"))
        return httpx.Response(200, text=text, headers={"X-SkyMind-Message-Type": mtype})

    real_client = httpx.Client
    monkeypatch.setattr(e2e.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    code = e2e.main(["--base-url", "http://test", "--ids", "offtopic_joke", "greeting_hi",
                     "--tier", "full", "--delay", "0", "--out", str(tmp_path)])
    assert code == 0
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "**PASS**" in report
    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert data["summary"]["passed"] == 2
    assert len(set(seen_sessions)) == 2  # a fresh session per case


def test_rate_limited_case_backs_off_then_reports_unscored(monkeypatch):
    monkeypatch.setattr(e2e.time, "sleep", lambda s: None)
    transport = httpx.MockTransport(lambda req: httpx.Response(429, text="slow down",
                                                                headers={"X-SkyMind-Message-Type": "notice"}))
    with httpx.Client(transport=transport) as client:
        r = e2e.run_case(client, "http://test", e2e.load_cases(ids=["greeting_hi"])[0], timeout=5)
    assert r.error and "429" in r.error


@pytest.mark.parametrize("text", [
    "Usually one bag of 7\u202fkg.",          # narrow no-break space, as gpt-oss writes it
    "Usually one bag of 7\u00a0kg.",          # no-break space
    "Usually one bag of 7 KG.",
])
def test_mentions_ignore_unicode_spacing_and_case(text):
    case = _case(must_mention_any=[["7 kg"]])
    assert e2e.score(case, _result(text)).passed is True


def test_must_not_contain_sees_through_non_breaking_hyphens():
    case = _case(must_not_contain=["check-in closes"])
    assert e2e.score(case, _result("Check\u2011in closes 45 minutes before.")).passed is False


def test_soft_hyphens_are_invisible_to_the_checks():
    case = _case(must_mention_any=[["boarding pass"]])
    assert e2e.score(case, _result("Print your board\u00ading pass.")).passed is True


@pytest.mark.parametrize("text, asked", [
    ("Where are you flying from?", True),
    ("To look up flights to Goa, I\u2019ll need a few more details:\n1. Origin\n2. Date", True),
    ("Please share your travel date.", True),
    ("Flights to Goa are cheapest in July.", False),
])
def test_asks_question_accepts_requests_without_a_question_mark(text, asked):
    case = _case(asks_question=True)
    assert e2e.score(case, _result(text)).passed is asked


def test_curly_apostrophe_no_data_reply_counts_as_honest():
    case = _case(live_data=True)
    r = e2e.score(case, _result("Live data isn’t available for this route right now. Please try again shortly."))
    assert r.passed is True and r.live_fares is False
