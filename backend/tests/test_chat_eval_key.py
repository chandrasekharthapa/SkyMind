from types import SimpleNamespace

from backend.routers.chat import _is_eval_client


def _req(header=None):
    return SimpleNamespace(headers={"X-SkyMind-Eval-Key": header} if header is not None else {})


def test_no_key_configured_exempts_nobody(monkeypatch):
    monkeypatch.delenv("CHAT_EVAL_KEY", raising=False)
    assert _is_eval_client(_req("")) is False
    assert _is_eval_client(_req("anything")) is False


def test_matching_key_is_exempt_and_others_are_not(monkeypatch):
    monkeypatch.setenv("CHAT_EVAL_KEY", "s3cret-eval-key")
    assert _is_eval_client(_req("s3cret-eval-key")) is True
    assert _is_eval_client(_req("wrong")) is False
    assert _is_eval_client(_req()) is False
