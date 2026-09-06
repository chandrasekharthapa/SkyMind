"""Tests for training_report.json generation (Milestone 8)."""
import json
import os
import tempfile
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from xgboost import XGBRegressor

from backend.ml.model_trainer import ModelTrainer
from backend.ml.evaluation import ModelEvaluator
from backend.ml.benchmark import ModelBenchmark


def _required_report_keys():
    return {
        "model_id", "forecast_horizon", "feature_set_version",
        "hyperparameters", "training_timestamp",
        "dataset", "evaluation",
    }


def test_training_report_build_method():
    """ModelTrainer._build_training_report returns all required keys."""
    trainer = ModelTrainer()
    from backend.ml.training_config import TrainingConfig
    config = TrainingConfig(feature_set_version="feature_set_v1", forecast_horizon=3)

    y_true = np.array([100.0, 200.0] * 50)
    y_pred = y_true + 10.0

    eval_report = ModelEvaluator().evaluate(
        y_true, y_pred,
        forecast_horizon=3, feature_set_version="feature_set_v1"
    )
    benchmark = ModelBenchmark().run(
        y_true, y_pred,
        # A benchmark with no baseline input is reported as `not_compared`; the
        # report these tests exercise should carry a real comparison.
        y_last_known=y_true - 10.0, y_train=y_true - 5.0)

    metadata = {
        "model_id": "model_h3d_test",
        "forecast_horizon": 3,
        "feature_set_version": "feature_set_v1",
        "dataset_hash": "abc123",
        "dataset_version": "DS_20260720",
        "training_rows": 80,
        "validation_rows": 20,
        "hyperparameters": config.hyperparameters,
        "training_timestamp": "2026-07-20T12:00:00+00:00",
        "git_commit": None,
        "config_hash": config.config_hash(),
        "env": {"python_version": "3.11"},
        "benchmark": benchmark.to_dict(),
    }

    report = trainer._build_training_report(
        model_id="model_h3d_test",
        config=config,
        metadata=metadata,
        eval_report=eval_report,
        benchmark_result=benchmark,
        importance_report=None,
        cv_report=None,
        training_duration=42.0,
    )

    for key in _required_report_keys():
        assert key in report, f"Missing key in training_report: {key}"


def test_training_report_dataset_section():
    """The 'dataset' section must contain hash and version."""
    trainer = ModelTrainer()
    from backend.ml.training_config import TrainingConfig
    config = TrainingConfig(feature_set_version="feature_set_v1", forecast_horizon=3)

    y_true = np.array([100.0] * 100)
    y_pred = y_true + 5.0
    eval_report = ModelEvaluator().evaluate(y_true, y_pred, forecast_horizon=3, feature_set_version="feature_set_v1")
    benchmark = ModelBenchmark().run(
        y_true, y_pred, y_last_known=y_true - 10.0, y_train=y_true - 5.0)

    metadata = {
        "model_id": "m", "forecast_horizon": 3, "feature_set_version": "feature_set_v1",
        "dataset_hash": "myhash", "dataset_version": "DS_X",
        "training_rows": 80, "validation_rows": 20,
        "hyperparameters": {}, "training_timestamp": "2026-07-20T00:00:00+00:00",
        "git_commit": None, "config_hash": None, "env": {}, "benchmark": None,
    }

    report = trainer._build_training_report(
        model_id="m", config=config, metadata=metadata,
        eval_report=eval_report, benchmark_result=benchmark,
        importance_report=None, cv_report=None, training_duration=10.0,
    )

    assert report["dataset"]["hash"] == "myhash"
    assert report["dataset"]["version"] == "DS_X"
    assert report["training_duration_seconds"] == 10.0
