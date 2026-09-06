"""Integration test — training pipeline shape (mocked DB, no real data needed)."""
import json
import os
import tempfile
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from xgboost import XGBRegressor

from backend.ml.training_config import TrainingConfig
from backend.ml.dataset_splitter import DatasetSplitter
from backend.ml.evaluation import ModelEvaluator
from backend.ml.benchmark import ModelBenchmark
from backend.ml import metrics as m


def _make_synthetic_dataset(n=300, seed=42, freq_hours=6) -> pd.DataFrame:
    """A frame shaped like a booking-curve extract, spanning weeks rather than hours.

    The spacing is load-bearing. `ModelTrainer` now embargoes the training fold by
    `horizon + lag_tolerance_days(horizon)` — 4.5 days at horizon 3 — and refuses
    to train when the purge leaves fewer than `minimum_training_rows`. At the
    hourly spacing this fixture used, 200 rows covered 8.3 days, the training fold
    covered the first 6.7 of them, and the embargo purged 107 of 160 rows: the test
    passed with 53 rows against a floor of 50. A fixture three rows from a
    data-sufficiency refusal reports the wrong failure for any change to `n`, so
    the observations are spread at `freq_hours` and the calendar features are
    derived from the resulting instant instead of from the row index.
    """
    rng = np.random.default_rng(seed)
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n):
        observed = base + timedelta(hours=i * freq_hours)
        elapsed_days = (observed - base).total_seconds() / 86400.0
        # Counts down over the whole frame instead of pinning to 1 after row 29,
        # so the feature still varies across every row the model sees.
        days_until_dep = max(1.0, 120.0 - elapsed_days)
        rows.append({
            "recorded_at": observed.isoformat(),
            "origin_code": "DEL",
            "destination_code": "BOM",
            "airline_code": "AI",
            "days_until_dep": days_until_dep,
            "urgency": 1.0 / days_until_dep,
            "day_of_week": observed.weekday(),
            "month": observed.month,
            "hour_of_day": observed.hour,
            "target_price": float(1500 + elapsed_days * 12 + rng.normal(0, 50)),
        })
    return pd.DataFrame(rows)


def test_pipeline_splitter_evaluator_benchmark():
    """DatasetSplitter → XGBRegressor → ModelEvaluator → ModelBenchmark end-to-end."""
    config = TrainingConfig(
        feature_set_version="feature_set_v1",
        forecast_horizon=3,
        random_seed=42,
        minimum_training_rows=50,
    )

    df = _make_synthetic_dataset(300)

    # Encode categoricals
    for col in ("origin_code", "destination_code", "airline_code"):
        df[col] = df[col].astype("category").cat.codes.astype(float) + 1

    feature_cols = [
        c for c in df.columns
        if c not in {"target_price", "recorded_at"}
    ]

    splitter = DatasetSplitter()
    split = splitter.split(df, target_col="target_price", test_size=0.2)

    # Verify chronological ordering
    train_max = pd.to_datetime(split.X_train["recorded_at"]).max()
    val_min = pd.to_datetime(split.X_val["recorded_at"]).min()
    assert train_max <= val_min, "Future leaked into training!"

    valid_feat_cols = [c for c in feature_cols if c in split.X_train.columns]
    X_tr = split.X_train[valid_feat_cols]
    X_vl = split.X_val[valid_feat_cols]

    model = XGBRegressor(n_estimators=50, random_state=config.random_seed)
    model.fit(X_tr, split.y_train)
    preds = model.predict(X_vl)

    eval_report = ModelEvaluator().evaluate(
        split.y_val.values, preds,
        forecast_horizon=config.forecast_horizon,
        feature_set_version=config.feature_set_version,
    )

    assert eval_report.prediction_count == split.val_rows
    assert eval_report.summary_metrics["mae"] > 0

    benchmark = ModelBenchmark().run(
        split.y_val.values, preds,
        # Both inputs are supplied because neither can be derived inside the
        # benchmark without reading the test labels. Without them the run is
        # correctly reported as `not_compared`, which is a real state but not
        # the one this test is about.
        y_last_known=(split.X_val["price"] if "price" in split.X_val.columns
                      else None),
        y_train=split.y_train,
        feature_set_version=config.feature_set_version,
    )
    assert benchmark.was_compared, (
        "no baseline could be computed: "
        + "; ".join(f"{s.name} ({s.reason})" for s in benchmark.skipped_baselines)
    )
    assert benchmark.verdict in ("improved", "unchanged", "regressed")
    assert benchmark.best_baseline in ("persistence", "train_mean")


def test_pipeline_full_flow_no_db(tmp_path):
    """Complete training pipeline flow without hitting the real database."""
    df = _make_synthetic_dataset(200)
    for col in ("origin_code", "destination_code", "airline_code"):
        df[col] = df[col].astype("category").cat.codes.astype(float) + 1

    config = TrainingConfig(
        feature_set_version="feature_set_v1",
        forecast_horizon=3,
        random_seed=42,
        minimum_training_rows=50,
        n_cv_folds=2,
    )

    with (
        patch("backend.ml.model_trainer.MODELS_DIR", str(tmp_path)),
        patch("backend.services.training_dataset_builder.training_dataset_builder.build",
              return_value=(df.copy(), df.copy())),
        patch("backend.services.model_registry.model_registry") as mock_reg,
    ):
        mock_reg.register_training_result.return_value = {"model_id": "test"}

        from backend.ml.model_trainer import ModelTrainer
        trainer = ModelTrainer()
        result, artifact = trainer.train(config, run_cross_validation=False)

    assert result.forecast_horizon == 3
    assert result.training_rows > 0
    assert artifact.exists()
    # Training report must be written
    assert os.path.isfile(artifact.report_path)
    with open(artifact.report_path) as f:
        report = json.load(f)
    assert "model_id" in report
    assert "evaluation" in report

    # The report has to say which experiment produced `evaluation`. Row counts
    # alone cannot distinguish a split that embargoed its labels from one that
    # did not, so the artifact records the split and this asserts against it:
    # a run that quietly stopped embargoing would still satisfy every line above.
    split = report["dataset"]["split"]
    assert split["strategy"] == "chronological_by_observation_time_with_embargo"
    assert split["embargo_days"] == 4.5, "horizon 3 + lag_tolerance_days(3)"
    assert split["rows_purged_by_embargo"] > 0, "the embargo was inert on this frame"
    assert split["train_rows"] == (split["train_rows_before_embargo"]
                                   - split["rows_purged_by_embargo"])
    assert split["boundary_is_strict"] is True
    assert split["embargo_is_effective"] is True
    assert split["gap_days"] >= 4.5
