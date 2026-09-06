"""Integration tests for model promotion — regressed models are never promoted."""
import pytest
from unittest.mock import MagicMock, patch

from backend.services.training_policy import TrainingPolicy


def test_policy_blocks_regressed_promotion():
    policy = TrainingPolicy()
    assert policy.should_promote({"mae": 500.0, "r2": 0.1}, "regressed") is False


def test_policy_allows_improved_promotion():
    policy = TrainingPolicy()
    assert policy.should_promote({"mae": 100.0, "r2": 0.9}, "improved") is True


def test_policy_allows_unchanged_by_default():
    policy = TrainingPolicy(allow_unchanged_promotion=True)
    assert policy.should_promote({"mae": 100.0, "r2": 0.85}, "unchanged") is True


def test_policy_blocks_unchanged_when_strict():
    policy = TrainingPolicy(
        promotion_requires_benchmark_improvement=True,
        allow_unchanged_promotion=False
    )
    assert policy.should_promote({"mae": 100.0, "r2": 0.85}, "unchanged") is False


def test_policy_blocks_a_model_that_was_never_compared():
    """`not_compared` must not pass a gate whose whole subject is the comparison.

    The gate was `verdict == "regressed"` → block, so every other string passed.
    With `allow_unchanged_promotion=True` — the default — the verdict was then
    never looked at again, and a model benchmarked against no baseline at all
    promoted on its metric thresholds alone.
    """
    policy = TrainingPolicy()
    assert policy.allow_unchanged_promotion is True, "fixture assumes the default"
    assert policy.should_promote({"mae": 1.0, "r2": 0.99}, "not_compared") is False
    # And it is the case a human should look at, even though it cannot promote.
    assert policy.requires_manual_review({"mae": 1.0}, "not_compared") is True


def test_policy_blocks_a_verdict_it_does_not_recognise():
    """Failing closed on an unknown verdict costs nothing: the old model keeps serving."""
    policy = TrainingPolicy()
    for verdict in ("", "unknown", "IMPROVED", "n/a", None):
        assert policy.should_promote({"mae": 1.0, "r2": 0.99}, verdict) is False, verdict


def test_policy_max_mae_gate():
    policy = TrainingPolicy(max_mae=200.0)
    assert policy.should_promote({"mae": 250.0, "r2": 0.9}, "improved") is False
    assert policy.should_promote({"mae": 150.0, "r2": 0.9}, "improved") is True


def test_policy_min_r2_gate():
    policy = TrainingPolicy(min_r2=0.8)
    assert policy.should_promote({"mae": 100.0, "r2": 0.6}, "improved") is False
    assert policy.should_promote({"mae": 100.0, "r2": 0.9}, "improved") is True


def test_registry_never_promotes_regressed():
    """End-to-end: even if ModelTrainer calls register_training_result with
    a regressed benchmark, the production slot must not change."""
    from backend.services.model_registry import ModelRegistry

    with patch("backend.services.model_registry.get_predictor", return_value=MagicMock()):
        reg = ModelRegistry(predictor=MagicMock())

    def _make_result(model_id, mae):
        r = MagicMock()
        r.model_id = model_id
        r.forecast_horizon = 3
        r.feature_set_version = "feature_set_v1"
        r.dataset_hash = "x"
        r.dataset_version = "v1"
        r.training_rows = 100
        r.validation_rows = 20
        r.metrics = {"mae": mae}
        r.training_duration_seconds = 1.0
        r.training_timestamp = "2026-07-20T00:00:00+00:00"
        r.git_commit = None
        r.config_hash = "cfg"
        return r

    def _bench(verdict):
        b = MagicMock()
        b.verdict = verdict
        b.improvement_pct = -0.3 if verdict == "regressed" else 0.1
        return b

    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(_make_result("good", 100.0), _bench("improved"))
        reg.register_training_result(_make_result("bad", 9999.0), _bench("regressed"))

    assert reg.get_slot("production")["model_id"] == "good"
