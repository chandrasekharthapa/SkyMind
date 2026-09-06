"""Test Suite for Model Readiness Service."""

import pytest

from backend.services.model_readiness import model_readiness_service


def test_model_readiness_reports_rather_than_raises():
    """A readiness probe must answer, including when there is no model at all.

    `check_readiness` called `PricePredictor.load()` unguarded, and `load()`
    raises `FileNotFoundError` on an empty models directory — so the three lines
    written to report "No active horizon models trained or loaded from disk"
    could never run, and the probe raised out of its caller instead of answering.
    """
    res = model_readiness_service.check_readiness()

    # `is_ready` and `reasons` must agree. Asserting only that status is one of
    # two strings, which is what this test used to do, cannot fail: those are the
    # only two values the function can return.
    assert res["is_ready"] == (res["reasons"] == []), res["reasons"]
    assert res["status"] == ("READY" if res["is_ready"] else "NOT_READY")


def test_model_readiness_cannot_be_ready_without_a_horizon():
    """No loaded horizon must mean NOT_READY, with a reason that says which.

    Holds in both directions of the current state: it does not assume the models
    directory is empty, it asserts the implication.
    """
    res = model_readiness_service.check_readiness()

    if not res["horizons_trained"]:
        assert not res["is_ready"], res
        assert any("model artifact" in r or "horizon models" in r for r in res["reasons"]), res["reasons"]
    else:
        # A horizon loaded, so the artifact passed the leak audit; nothing about
        # the model itself may then appear as a blocking reason.
        assert not any(r.startswith("Refused artifact") and f"{h}d:" in r
                       for h in res["horizons_trained"] for r in res["reasons"]), res["reasons"]


def test_model_readiness_publishes_refusals():
    """Refused artifacts must be reported, not silently absent.

    A directory full of .pkl files that still reports NOT_READY is unexplainable
    unless the refusal reasons travel with the verdict.
    """
    res = model_readiness_service.check_readiness()
    assert "refused_artifacts" in res
    for item in res["refused_artifacts"]:
        assert any(item in reason for reason in res["reasons"]), (item, res["reasons"])
