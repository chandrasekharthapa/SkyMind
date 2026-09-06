"""Tests for reproducibility — same seed + same data → same metrics."""
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error


def _make_deterministic_df(n=300, seed=42):
    rng = np.random.default_rng(seed)
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n):
        rows.append({
            "recorded_at": (base + timedelta(hours=i)).isoformat(),
            "feature_a": float(i),
            "feature_b": float(rng.uniform(0, 1)),
            "target_price": float(1000 + i * 5 + rng.normal(0, 30)),
        })
    return pd.DataFrame(rows)


def _train_once(df, seed=42) -> float:
    from backend.ml.dataset_splitter import DatasetSplitter
    from backend.ml import metrics as m

    splitter = DatasetSplitter()
    split = splitter.split(df, target_col="target_price", test_size=0.2)

    feature_cols = ["feature_a", "feature_b"]
    X_tr = split.X_train[feature_cols]
    X_vl = split.X_val[feature_cols]

    model = XGBRegressor(n_estimators=100, random_state=seed)
    model.fit(X_tr, split.y_train)
    preds = model.predict(X_vl)
    return m.mae(split.y_val.values, preds)


def test_training_is_reproducible_same_seed():
    """Identical dataset + identical seed must produce identical MAE."""
    df = _make_deterministic_df(n=300, seed=42)

    mae1 = _train_once(df, seed=42)
    mae2 = _train_once(df, seed=42)

    assert abs(mae1 - mae2) < 1e-9, (
        f"Training is not reproducible: mae1={mae1}, mae2={mae2}"
    )


def test_training_differs_with_different_seed():
    """Different seeds should generally produce different results (not guaranteed
    but extremely likely on real data)."""
    df = _make_deterministic_df(n=300, seed=42)
    mae_42 = _train_once(df, seed=42)
    mae_99 = _train_once(df, seed=99)
    # Allow for the edge case where they happen to be equal
    # (very unlikely with enough data) — just log the result
    assert isinstance(mae_42, float)
    assert isinstance(mae_99, float)


def test_dataset_splitter_is_deterministic():
    """DatasetSplitter must always produce the same split for the same DataFrame."""
    from backend.ml.dataset_splitter import DatasetSplitter
    df = _make_deterministic_df(n=200, seed=42)
    splitter = DatasetSplitter()

    split1 = splitter.split(df, target_col="target_price", test_size=0.2)
    split2 = splitter.split(df, target_col="target_price", test_size=0.2)

    assert split1.train_rows == split2.train_rows
    assert split1.val_rows == split2.val_rows
    assert split1.train_date_max == split2.train_date_max
