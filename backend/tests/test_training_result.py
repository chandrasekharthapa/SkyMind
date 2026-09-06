"""Tests for TrainingResult."""
import json
from backend.ml.training_result import TrainingResult


def _make_result(**overrides) -> TrainingResult:
    defaults = dict(
        model_id="model_h3d_20260720_120000",
        forecast_horizon=3,
        feature_set_version="feature_set_v1",
        dataset_hash="abc123",
        dataset_version="DS_20260720_120000",
        training_rows=500,
        validation_rows=100,
        metrics={"mae": 150.0, "rmse": 200.0, "r2": 0.85},
        training_duration_seconds=42.5,
        training_timestamp="2026-07-20T12:00:00+00:00",
    )
    defaults.update(overrides)
    return TrainingResult(**defaults)


def test_training_result_fields_present():
    r = _make_result()
    assert r.model_id.startswith("model_h3d")
    assert r.forecast_horizon == 3
    assert r.training_rows == 500
    assert r.metrics["mae"] == 150.0


def test_training_result_is_immutable():
    import pytest
    r = _make_result()
    with pytest.raises((AttributeError, TypeError)):
        r.forecast_horizon = 99  # frozen


def test_training_result_to_dict():
    r = _make_result()
    d = r.to_dict()
    assert isinstance(d, dict)
    assert "model_id" in d
    assert "metrics" in d


def test_training_result_to_json():
    r = _make_result()
    raw = r.to_json()
    parsed = json.loads(raw)
    assert parsed["model_id"] == r.model_id


def test_make_model_id_contains_horizon():
    mid = TrainingResult.make_model_id(7, "20260720_120000")
    assert "h7d" in mid
    assert "20260720" in mid
