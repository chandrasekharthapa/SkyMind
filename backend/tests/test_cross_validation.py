"""Tests for TimeSeriesCrossValidator — the public `validate` surface.

Two of the five tests here could not fail.

`test_cross_validation_rolling_produces_report` asserted only
`isinstance(report, CrossValidationReport)`. `validate` returns one
unconditionally, so the assertion held for a rolling run that scored *zero*
folds — which is exactly what the rolling window did at `n_folds=1`, and what it
did with a training slice narrower than one fold at every other `n_folds`. This
test is the reason that went unnoticed. `test_cross_validation_expanding_produces_report`
asked for three folds and accepted `n_folds >= 1`, so it would also have passed a
run that silently dropped two of them.

The frame was also built with a bare `np.random.uniform`, i.e. a different frame
on every run, which buys nothing for a smoke test and means a failure here could
not be reproduced from the file alone. It is seeded now.

`XGBRegressor` is gone: the errors these tests check for are raised before a model
is touched, and the scored runs are about fold arithmetic, not about the fit. See
`backend/tests/linear_estimator.py`. Fold-boundary and embargo behaviour is
covered in depth by `test_time_series_validation.py`; this module stays the
smoke test for the call signature and the two refusals.
"""
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from backend.ml.cross_validation import TimeSeriesCrossValidator, CrossValidationReport
from backend.tests.linear_estimator import LinearOnFirstFeature


def _make_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n):
        rows.append({
            "recorded_at": (base + timedelta(hours=i)).isoformat(),
            "feature_a": float(i),
            "feature_b": float(np.sin(i / 10)),
            "target_price": float(1000 + i * 5 + rng.uniform(-50, 50)),
        })
    return pd.DataFrame(rows)


def test_cross_validation_expanding_produces_report():
    df = _make_df(300)
    cv = TimeSeriesCrossValidator()
    report = cv.validate(
        df, LinearOnFirstFeature(), ["feature_a", "feature_b"], "target_price",
        n_folds=3, strategy="expanding",
        feature_set_version="feature_set_v1", forecast_horizon=3,
        min_train_rows=20, random_seed=42,
    )
    assert isinstance(report, CrossValidationReport)
    # Three folds were asked for and 300 rows at min_train_rows=20 can supply
    # three. `>= 1` was the old bound and would have passed a run that dropped two.
    assert report.n_folds == 3, [w["skip_reason"] for w in report.fold_windows]
    assert all(w["scored"] for w in report.fold_windows)
    assert report.strategy == "expanding"


def test_cross_validation_rolling_produces_report():
    df = _make_df(300)
    cv = TimeSeriesCrossValidator()
    report = cv.validate(
        df, LinearOnFirstFeature(), ["feature_a", "feature_b"], "target_price",
        n_folds=3, strategy="rolling",
        feature_set_version="feature_set_v1", forecast_horizon=7,
        min_train_rows=20, random_seed=42,
    )
    assert isinstance(report, CrossValidationReport)
    # The claim the isinstance check never made: the run measured something.
    assert report.n_folds == 3, [w["skip_reason"] for w in report.fold_windows]
    assert not np.isnan(report.avg_metrics["mae"])
    assert report.strategy == "rolling"


def test_cross_validation_avg_metrics_keys():
    df = _make_df(300)
    cv = TimeSeriesCrossValidator()
    report = cv.validate(
        df, LinearOnFirstFeature(), ["feature_a", "feature_b"], "target_price",
        n_folds=3, strategy="expanding",
        feature_set_version="feature_set_v1", forecast_horizon=3,
        min_train_rows=20,
    )
    assert "mae" in report.avg_metrics
    assert "rmse" in report.avg_metrics
    assert "r2" in report.avg_metrics
    # A key present with a NaN behind it is the state of a report that scored
    # nothing, so presence alone is not the property worth asserting.
    assert not any(np.isnan(report.avg_metrics[k]) for k in ("mae", "rmse", "r2"))


def test_cross_validation_raises_on_unknown_strategy():
    df = _make_df(100)
    cv = TimeSeriesCrossValidator()
    with pytest.raises(ValueError, match="Unknown validation_strategy"):
        cv.validate(
            df, LinearOnFirstFeature(), ["feature_a"], "target_price",
            n_folds=2, strategy="bad_strategy",
            feature_set_version="feature_set_v1", forecast_horizon=3,
        )


def test_cross_validation_no_time_column_raises():
    df = pd.DataFrame({"feature_a": [1, 2, 3], "target_price": [10, 20, 30]})
    cv = TimeSeriesCrossValidator()
    with pytest.raises(ValueError, match="No time column"):
        cv.validate(
            df, LinearOnFirstFeature(), ["feature_a"], "target_price",
            n_folds=2, strategy="expanding",
            feature_set_version="feature_set_v1", forecast_horizon=3,
        )
