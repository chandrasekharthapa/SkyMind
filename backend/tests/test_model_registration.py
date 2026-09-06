"""Tests for ModelRegistry registration slots (Milestone 5)."""
import pytest
from unittest.mock import MagicMock, patch


def _make_result(horizon=3, mae=150.0, model_id=None):
    result = MagicMock()
    result.model_id = model_id or f"model_h{horizon}d_20260720_120000"
    result.forecast_horizon = horizon
    result.feature_set_version = "feature_set_v1"
    result.dataset_hash = "abc123"
    result.dataset_version = "DS_20260720_120000"
    result.training_rows = 500
    result.validation_rows = 100
    result.metrics = {"mae": mae, "rmse": mae * 1.3, "r2": 0.85}
    result.training_duration_seconds = 42.5
    result.training_timestamp = "2026-07-20T12:00:00+00:00"
    result.git_commit = None
    result.config_hash = "abc123"
    return result


def _make_benchmark(verdict="improved", improvement_pct=0.05):
    bm = MagicMock()
    bm.verdict = verdict
    bm.improvement_pct = improvement_pct
    return bm


def _make_registry():
    """Create a ModelRegistry without loading PricePredictor."""
    from backend.services.model_registry import ModelRegistry
    with patch("backend.services.model_registry.get_predictor", return_value=MagicMock()):
        reg = ModelRegistry(predictor=MagicMock())
    return reg


def test_registration_updates_latest_slot():
    reg = _make_registry()
    result = _make_result()
    bm = _make_benchmark("improved")
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(result, bm)
    latest = reg.get_slot("latest")
    assert latest is not None
    assert latest["model_id"] == result.model_id


def test_registration_updates_production_when_improved():
    reg = _make_registry()
    result = _make_result()
    bm = _make_benchmark("improved")
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(result, bm)
    prod = reg.get_slot("production")
    assert prod is not None
    assert prod["model_id"] == result.model_id


def test_regressed_model_not_promoted_to_production():
    reg = _make_registry()
    # First: put a good model in production
    good = _make_result(mae=100.0, model_id="good_model")
    bm_good = _make_benchmark("improved")
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(good, bm_good)

    # Second: register a regressed model
    bad = _make_result(mae=500.0, model_id="bad_model")
    bm_bad = _make_benchmark("regressed", improvement_pct=-0.4)
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(bad, bm_bad)

    # Production must still be the good model
    prod = reg.get_slot("production")
    assert prod["model_id"] == "good_model", (
        f"Regressed model wrongly promoted to production: {prod['model_id']}"
    )


def test_best_slot_tracks_lowest_mae():
    reg = _make_registry()
    high_mae = _make_result(mae=300.0, model_id="high_mae")
    low_mae = _make_result(mae=50.0, model_id="low_mae")
    bm = _make_benchmark("improved")
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(high_mae, bm)
        reg.register_training_result(low_mae, bm)
    best = reg.get_slot("best")
    assert best["model_id"] == "low_mae"


def test_archived_slot_grows_on_production_replacement():
    reg = _make_registry()
    r1 = _make_result(mae=200.0, model_id="first")
    r2 = _make_result(mae=150.0, model_id="second")
    bm = _make_benchmark("improved")
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(r1, bm)
        reg.register_training_result(r2, bm)
    archived = reg.get_slot("archived")
    assert len(archived) == 1
    assert archived[0]["model_id"] == "first"


def test_a_model_benchmarked_against_nothing_is_not_promoted():
    """`not_compared` is the verdict `ModelBenchmark` returns with no baseline.

    The gate was `benchmark.verdict != "regressed"`, which is true of every
    string it has never heard of, so a model whose benchmark could not compute a
    single baseline replaced production on the strength of a verdict that means
    "we did not check".
    """
    reg = _make_registry()
    good = _make_result(mae=100.0, model_id="good_model")
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(good, _make_benchmark("improved"))

    uncompared = _make_result(mae=40.0, model_id="uncompared_model")
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(
            uncompared, _make_benchmark("not_compared", improvement_pct=0.0))

    assert reg.get_slot("production")["model_id"] == "good_model"
    # It is still the best MAE on record and still the latest run — the refusal
    # is about replacing what is serving, not about hiding the result.
    assert reg.get_slot("best")["model_id"] == "uncompared_model"
    assert reg.get_slot("latest")["model_id"] == "uncompared_model"


def test_a_run_with_no_benchmark_object_at_all_is_not_promoted():
    """`benchmark is None` used to be an explicit pass straight to production."""
    reg = _make_registry()
    good = _make_result(mae=100.0, model_id="good_model")
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(good, _make_benchmark("improved"))

    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(
            _make_result(mae=10.0, model_id="unbenchmarked"), None)

    assert reg.get_slot("production")["model_id"] == "good_model"
    assert reg.get_slot("latest")["benchmark_verdict"] == "unknown"


def test_the_registry_entry_names_the_baseline_the_verdict_is_against():
    reg = _make_registry()
    bm = _make_benchmark("improved")
    bm.best_baseline = "persistence"
    bm.best_baseline_value = 20.0
    with patch.object(reg, "_persist_registry"):
        reg.register_training_result(_make_result(), bm)
    entry = reg.get_slot("production")
    assert entry["benchmark_baseline"] == "persistence"
    assert entry["benchmark_baseline_value"] == 20.0
