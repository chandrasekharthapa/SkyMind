"""Unit tests for evaluation resilience and environment hardening.

These lock in the fixes to the defect class the eval suite was riddled with: a
result that could not fail. Three of them are regression tests for specific bugs
and say so.
"""

import pytest
import os
from backend.evals.environment import (
    environment_inspector,
    ProviderHealthReport,
    ServiceHealthStatus,
)
from backend.evals.registry import EvaluatorResult
from backend.evals.evaluators.base import BaseEvaluator, PASS_RATIO_THRESHOLD
from backend.evals.evaluators.deterministic.groundedness import GroundednessEvaluator
from backend.evals.reports.markdown import generate_markdown_report


def _health_summary(**overrides):
    """A summary whose `provider_health` block is the real inspector shape.

    Built from `ProviderHealthReport` rather than hand-written, because the two
    tests that used to cover the markdown report hand-built a *flat* dict
    (`openai_api_key_configured`, `langsmith_installed`, ...) that no summary has
    ever contained. The report read those flat keys, so its infrastructure table
    was wired to nothing in production while looking covered in test. Constructing
    the fixture from the model makes that particular lie impossible to retell.
    """
    report = ProviderHealthReport(
        overall_health="HEALTHY",
        benchmark_validity="FULL",
        openai=ServiceHealthStatus(name="OpenAI", configured=True, healthy=True,
                                   reachable=True, authenticated=True,
                                   quota_available=True, current_mode="PRIMARY",
                                   reason="API key configured"),
        langsmith=ServiceHealthStatus(name="LangSmith", configured=True, healthy=True,
                                      current_mode="ACTIVE",
                                      reason="LangSmith SDK & API key active"),
        filesystem=ServiceHealthStatus(name="Filesystem", configured=True, healthy=True,
                                       current_mode="ACTIVE",
                                       reason="Results directory is writable"),
        dataset=ServiceHealthStatus(name="Dataset", configured=True, healthy=True,
                                    current_mode="ACTIVE",
                                    reason="6 case(s) loaded, schema validated"),
    )
    summary = {
        "dataset_version": "2.0.0",
        "tier": "smoke",
        "git_sha": "test_sha",
        "evaluation_result": "PASS",
        "benchmark_validity": "FULL",
        "environment": report.model_dump(),
        "provider_health": report.model_dump(),
        "infrastructure": {"judge_status": "ACTIVE", "openai_mode": "PRIMARY"},
        "planner_provenance": {"planner_status": "PRIMARY", "planner_source": "hybrid",
                              "planner_model": "meta/llama-3.1-70b-instruct",
                              "planner_reason": "Executed primary planner"},
        "total_cases": 6,
        "executed_evaluators_count": 5,
        "skipped_evaluators_count": 1,
        "passed_evaluators_count": 5,
        "failed_evaluators_count": 0,
        "overall_success_rate": 100.0,
        "evaluator_results": {
            "intent_accuracy": {"category": "deterministic", "status": "PASS",
                                "score": 1.0, "reason": "5/5 item(s) passed"},
            "groundedness": {"category": "deterministic", "status": "SKIPPED",
                             "score": None, "reason": "No query recorded on the run"},
        },
        "warnings": [],
    }
    summary.update(overrides)
    return summary


def test_environment_inspector():
    report = environment_inspector.inspect()
    assert report.langsmith.name == "LangSmith"
    assert report.openai.name == "OpenAI"


def test_inspector_actually_checks_the_dataset():
    """Regression: `ProviderHealthReport.dataset` was never assigned by `inspect()`.

    It kept its field default (`configured=False, healthy=False,
    reason="Unchecked"`) forever, and the markdown report printed a hardcoded
    `| Dataset | YES | YES | HEALTHY |` row instead of reading it. So the one
    component whose health decides whether the benchmark means anything was the
    one component nothing measured.
    """
    report = environment_inspector.inspect(dataset_version="2.0.0", tier="smoke")
    assert report.dataset.reason != "Unchecked"
    assert report.dataset.healthy is True
    assert report.dataset.current_mode == "ACTIVE"


def test_inspector_invalidates_the_benchmark_when_no_cases_load():
    report = environment_inspector.inspect(dataset_version="0.0.0-nonexistent")
    assert report.dataset.healthy is False
    assert report.benchmark_validity == "INVALID"
    assert report.overall_health == "FAILED"


def test_groundedness_skip_is_not_a_pass():
    """Regression: this evaluator returned `SKIPPED` with `passed=True` and, when
    not skipped, an unconditional `score=1.0` for a comparison it never made."""
    evaluator = GroundednessEvaluator()
    res = evaluator.evaluate_item({}, {})
    assert res.status == "SKIPPED"
    assert res.score is None
    assert res.passed is False
    assert "query" in res.reason.lower()


def test_groundedness_does_not_depend_on_an_api_key():
    """It is a deterministic text check; gating it behind `OPENAI_API_KEY` is how
    it came to skip on every CI run and report `passed=True` while doing so."""
    orig_key = os.environ.pop("OPENAI_API_KEY", None)
    try:
        res = GroundednessEvaluator().evaluate_item({}, {
            "query": "cheapest flight from Delhi to Bombay tomorrow",
            "entities": {"origin": "DEL", "destination": "BOM"},
        })
        assert res.status == "PASS"
        assert res.score == 1.0
    finally:
        if orig_key:
            os.environ["OPENAI_API_KEY"] = orig_key


def test_groundedness_can_fail_on_an_invented_entity():
    res = GroundednessEvaluator().evaluate_item({}, {
        "query": "flights to Bombay tomorrow",
        "entities": {"origin": "DEL", "destination": "BOM"},
    })
    assert res.status == "FAIL"
    assert res.passed is False
    assert any("origin" in v for v in res.details["violations"])


# --------------------------------------------------------------------------- #
# The coordinator's two "cannot certify anything" verdicts.
#
# Both were asserted in the changelog and pinned by nothing. The success-rate half
# is covered by `test_evals_v2.py`, but only conditionally — that test runs the real
# smoke suite, where the deterministic evaluators do execute, so its `executed == 0`
# branch has never been taken on any machine. These take it deliberately.
# --------------------------------------------------------------------------- #


class _AlwaysUnavailable:
    """An evaluator that reports the status a missing dependency produces.

    `passed=True` is the point, not an oversight: `INFRASTRUCTURE_UNAVAILABLE` results
    carry it, which is how they used to be counted as executed *and* as passes.
    """

    category = "deterministic"

    def __init__(self, config=None):
        self.config = config

    def evaluate_batch(self, items):
        return EvaluatorResult(
            evaluator_name="always_unavailable", category="deterministic",
            score=None, status="INFRASTRUCTURE_UNAVAILABLE", passed=True,
            reason="No Supabase credentials in this environment",
        )


@pytest.mark.asyncio
async def test_a_run_where_every_evaluator_skipped_fails_and_reports_no_rate(tmp_path):
    """Nothing measured is not a pass, and there is no number for it.

    `overall_success_rate` ended `else 100.0`, and `failed_count` is zero when nothing
    ran, so this exact state — every evaluator skipping for want of a credential —
    produced a 100% rate and a PASS verdict. It is the state a CI runner with no keys
    is *in*, which is what made the green report worthless rather than merely wrong.
    """
    from backend.evals.config import EvaluationConfig
    from backend.evals import evaluator as evaluator_module

    config = EvaluationConfig(dataset_version="2.0.0", tier="smoke",
                              output_directory=str(tmp_path / "results"))
    ev = evaluator_module.AIEvaluator(config=config)
    monkey = {"always_unavailable": _AlwaysUnavailable(config)}
    orig = evaluator_module.evaluator_registry.instantiate_all
    evaluator_module.evaluator_registry.instantiate_all = lambda cfg: monkey
    try:
        summary = await ev.run_evaluation(tier="smoke")
    finally:
        evaluator_module.evaluator_registry.instantiate_all = orig

    assert summary["executed_evaluators_count"] == 0, summary
    assert summary["skipped_evaluators_count"] == 1, summary
    assert summary["overall_success_rate"] is None, summary
    assert summary["evaluation_result"] == "FAIL", summary
    # And the metrics that used to default to their best possible value.
    assert summary["intent_accuracy"] is None, summary
    assert summary["entity_accuracy"] is None, summary
    assert summary["tool_f1_score"] is None, summary
    assert summary["p95_latency_ms"] is None, summary


class _AlwaysPasses:
    """A scored, passing evaluator, so a FAIL verdict must come from somewhere else."""

    category = "deterministic"

    def __init__(self, config=None):
        self.config = config

    def evaluate_batch(self, items):
        return EvaluatorResult(
            evaluator_name="always_passes", category="deterministic",
            score=1.0, status="PASS", passed=True,
            reason=f"{len(items)}/{len(items)} item(s) passed",
        )


@pytest.mark.asyncio
async def test_a_schema_invalid_benchmark_cannot_pass(monkeypatch, tmp_path):
    """A corpus that failed its own schema check invalidates the run that used it.

    The registry is stubbed to a single passing evaluator, so `failed_count` is 0 and
    `executed_count` is 1: FAIL cannot be arriving from a failing measurement, which
    is what makes this a test of the schema-error branch rather than of the smoke
    suite's current scores. (Run against the real registry it passed for the wrong
    reason — an evaluator fails in a sandbox with no database, so the verdict was FAIL
    either way.) Asserted on `dataset_schema_errors` being non-empty rather than on an
    unloadable version, which is a different failure (`total_cases == 0`) with its own
    early return.
    """
    from backend.evals.config import EvaluationConfig
    from backend.evals import evaluator as evaluator_module
    from backend.evals.datasets.loader import dataset_loader

    real_load = dataset_loader.load_dataset

    def _load_then_report_an_error(*args, **kwargs):
        records = real_load(*args, **kwargs)
        dataset_loader.last_schema_errors = ["case_003: duplicate id"]
        return records

    monkeypatch.setattr(dataset_loader, "load_dataset", _load_then_report_an_error)

    config = EvaluationConfig(dataset_version="2.0.0", tier="smoke",
                              output_directory=str(tmp_path / "results"))
    stub = {"always_passes": _AlwaysPasses(config)}
    orig = evaluator_module.evaluator_registry.instantiate_all
    evaluator_module.evaluator_registry.instantiate_all = lambda cfg: stub
    try:
        summary = await evaluator_module.AIEvaluator(config=config).run_evaluation(tier="smoke")
    finally:
        evaluator_module.evaluator_registry.instantiate_all = orig

    assert summary["dataset_schema_errors"] == ["case_003: duplicate id"], summary
    assert summary["executed_evaluators_count"] == 1, summary
    assert summary["failed_evaluators_count"] == 0, summary
    assert summary["overall_success_rate"] == 100.0, summary
    assert summary["benchmark_validity"] == "INVALID", summary
    assert summary["evaluation_result"] == "FAIL", (
        "a 100% success rate on a benchmark whose schema did not hold is still a FAIL")


def test_groundedness_resolves_an_airline_by_name():
    """`airline_code="UK"` is grounded in a query naming Vistara: the code and the
    name are the same carrier, and a literal text search called that a violation."""
    res = GroundednessEvaluator().evaluate_item({}, {
        "query": "What about Vistara for the same route?",
        "entities": {"airline_code": "UK"},
    })
    assert res.status == "PASS"


def test_groundedness_counts_context_as_evidence():
    actual = {
        "query": "What about Vistara for the same route?",
        "entities": {"origin": "DEL", "destination": "BOM", "airline_code": "UK"},
    }
    assert GroundednessEvaluator().evaluate_item({}, actual).status == "FAIL"
    with_context = dict(actual, context={"origin": "Delhi", "destination": "Mumbai"})
    assert GroundednessEvaluator().evaluate_item({}, with_context).status == "PASS"


class SampleSkippedEvaluator(BaseEvaluator):
    name = "sample_skipped"
    category = "deterministic"
    feedback_key = "sample_key"

    def evaluate_item(self, expected, actual):
        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=None,
            status="SKIPPED",
            passed=True,
            reason="External service unavailable"
        )


class SampleUnscoredEvaluator(BaseEvaluator):
    """Executes every item and never produces a number."""

    name = "sample_unscored"
    category = "deterministic"
    feedback_key = "sample_key"

    def evaluate_item(self, expected, actual):
        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=None,
            status="PASS",
            passed=True,
            reason="ran but measured nothing"
        )


class SampleMixedEvaluator(BaseEvaluator):
    """Passes items whose actual dict is truthy, fails the rest."""

    name = "sample_mixed"
    category = "deterministic"
    feedback_key = "sample_key"

    def evaluate_item(self, expected, actual):
        ok = bool(actual)
        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=1.0 if ok else 0.0,
            status="PASS" if ok else "FAIL",
            passed=ok,
            reason="ok" if ok else "not ok"
        )


def test_skipped_batch_does_not_claim_to_have_passed():
    batch_res = SampleSkippedEvaluator().evaluate_batch([{"expected": {}, "actual": {}}])
    assert batch_res.status == "SKIPPED"
    assert batch_res.score is None
    assert batch_res.passed is False
    assert batch_res.reason == "External service unavailable"


def test_executed_but_unscored_batch_is_an_error_not_a_skip():
    """Regression: `if not executed_scores` conflated "nothing ran" with "things
    ran and none produced a number". The second is a broken evaluator."""
    batch_res = SampleUnscoredEvaluator().evaluate_batch(
        [{"expected": {}, "actual": {"x": 1}} for _ in range(3)])
    assert batch_res.status == "ERROR"
    assert batch_res.passed is False
    assert batch_res.details["executed"] == 3
    assert batch_res.details["scored"] == 0


def test_pass_ratio_uses_the_executed_denominator():
    """Regression: the ratio was `passed_count / len(executed_scores)`, and
    `passed_count` counts items that returned no score. On such a batch the ratio
    could exceed 1.0, which made the 0.80 threshold impossible to miss."""
    items = [{"expected": {}, "actual": {"x": 1}}] * 4 + [{"expected": {}, "actual": {}}]
    batch_res = SampleMixedEvaluator().evaluate_batch(items)
    assert batch_res.details["pass_ratio"] == pytest.approx(0.8)
    assert batch_res.details["pass_ratio"] <= 1.0
    assert batch_res.details["pass_ratio_threshold"] == PASS_RATIO_THRESHOLD
    assert batch_res.passed is True

    harsher = SampleMixedEvaluator().evaluate_batch(
        [{"expected": {}, "actual": {"x": 1}}] * 3 + [{"expected": {}, "actual": {}}] * 2)
    assert harsher.details["pass_ratio"] == pytest.approx(0.6)
    assert harsher.status == "FAIL"
    assert harsher.passed is False


def test_markdown_report_formatting():
    report_md = generate_markdown_report(_health_summary())
    assert "# SkyMind Copilot -- Evaluation Report" in report_md
    assert "## Executive Summary" in report_md
    assert "| `groundedness` | `deterministic` | `SKIPPED` | --- |" in report_md


def test_markdown_report_reads_the_real_health_shape():
    """The infrastructure table must be populated from `provider_health`, not from
    literal text and not from flat keys nothing produces."""
    report_md = generate_markdown_report(_health_summary())
    assert "Results directory is writable" in report_md
    assert "6 case(s) loaded, schema validated" in report_md
    assert "API key configured" in report_md
    assert "- [x] Dataset loaded and verified" in report_md


def test_markdown_report_has_no_optimistic_defaults():
    """Regression: `generate_markdown_report({})` produced a clean passing report.

    `evaluation_result` defaulted to PASS, `overall_health` to HEALTHY,
    `benchmark_validity` to FULL, and three infrastructure rows were literal
    `| YES | YES | HEALTHY |` text.
    """
    report_md = generate_markdown_report({})
    assert "PASS" not in report_md
    assert "HEALTHY" not in report_md
    assert "FULL" not in report_md
    assert "UNKNOWN" in report_md
    assert "NOT_RUN" in report_md


def test_markdown_report_does_not_invent_a_success_rate():
    report_md = generate_markdown_report(_health_summary(overall_success_rate=None))
    assert "n/a (no evaluator executed)" in report_md
    assert "100.0%" not in report_md
