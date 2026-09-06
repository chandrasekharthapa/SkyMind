"""Tests for ModelTrainer (mocked end-to-end)."""
import json
import os
import tempfile
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from backend.ml.training_config import TrainingConfig
from backend.ml.training_result import TrainingResult
from backend.ml.model_artifact import ModelArtifact


def _make_fake_dataset(n=200):
    """Synthetic feature-engineered DataFrame with target_price."""
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n):
        rows.append({
            "recorded_at": (base + timedelta(hours=i)).isoformat(),
            "origin_code": "DEL",
            "destination_code": "BOM",
            "airline_code": "AI",
            "feature_a": float(i),
            "feature_b": float(np.sin(i / 10)),
            "target_price": float(1000 + i * 5 + np.random.uniform(-50, 50)),
        })
    df = pd.DataFrame(rows)
    return df, df.copy()  # (raw, features)


def test_model_trainer_returns_result_and_artifact():
    """Full mock of ModelTrainer.train() — no database, no files."""
    config = TrainingConfig(
        feature_set_version="feature_set_v1",
        forecast_horizon=3,
        minimum_training_rows=50,
        n_cv_folds=2,
    )

    df_raw, df_feat = _make_fake_dataset(200)

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("backend.ml.model_trainer.MODELS_DIR", tmpdir),
            patch(
                "backend.ml.model_trainer.ModelTrainer.train",
                autospec=True,
            ) as mock_train,
        ):
            mock_result = MagicMock(spec=TrainingResult)
            mock_result.model_id = "model_h3d_test"
            mock_result.metrics = {"mae": 120.0, "rmse": 180.0, "r2": 0.88}
            mock_artifact = MagicMock(spec=ModelArtifact)
            mock_artifact.model_path = os.path.join(tmpdir, "model.pkl")
            mock_artifact.report_path = os.path.join(tmpdir, "report.json")
            mock_train.return_value = (mock_result, mock_artifact)

            from backend.ml.model_trainer import ModelTrainer
            trainer = ModelTrainer()
            result, artifact = trainer.train(config)

            assert result.model_id == "model_h3d_test"
            assert artifact.model_path.endswith(".pkl")


def test_model_trainer_training_result_fields():
    """Smoke-test that TrainingResult fields are valid types."""
    from backend.ml.training_result import TrainingResult
    r = TrainingResult(
        model_id="m1",
        forecast_horizon=3,
        feature_set_version="feature_set_v1",
        dataset_hash="abc",
        dataset_version="v1",
        training_rows=400,
        validation_rows=100,
        metrics={"mae": 120.0},
        training_duration_seconds=30.0,
        training_timestamp="2026-07-20T12:00:00+00:00",
    )
    assert isinstance(r.training_rows, int)
    assert isinstance(r.metrics, dict)


def test_model_trainer_raises_on_insufficient_rows():
    """ModelTrainer must raise when dataset is too small."""
    config = TrainingConfig(
        feature_set_version="feature_set_v1",
        forecast_horizon=3,
        minimum_training_rows=1000,
    )

    small_df = pd.DataFrame([{
        "recorded_at": "2026-01-01",
        "origin_code": "DEL",
        "destination_code": "BOM",
        "airline_code": "AI",
        "feature_a": 1.0,
        "target_price": 1000.0,
    }])

    with (
        patch("backend.services.training_dataset_builder.training_dataset_builder.build",
              return_value=(small_df, small_df)),
        patch("backend.ml.model_trainer.MODELS_DIR", tempfile.mkdtemp()),
    ):
        from backend.ml.model_trainer import ModelTrainer
        trainer = ModelTrainer()
        with pytest.raises(RuntimeError, match="Insufficient training rows"):
            trainer.train(config)
