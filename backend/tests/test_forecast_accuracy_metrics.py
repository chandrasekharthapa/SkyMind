"""Forecast accuracy, measured where it can actually be measured.

This module used to assert `"mae" in metrics` … `"drift" in metrics` on
`PredictionConsistencyValidator.validate_consistency` — a near-duplicate of
`test_prediction_accuracy_metrics.py`, over the same five keys that were fixed at
`0.0`. Forecast error cannot be computed at prediction time: it needs the fare
that was realised after the horizon elapsed. `forecast_evaluation_scheduler`
resolves each forecast against that later fare, and `ForecastEvaluator` aggregates
the outcomes, so this is where accuracy has to be tested.

The property that matters most here is the one the old code got backwards: with no
usable outcome, the metrics are undefined, not zero. Zero MAE, RMSE and MAPE
describe a *perfect* forecaster.
"""
import math

import pandas as pd

from backend.ml import metrics as m
from backend.services.forecast_evaluator import forecast_evaluator


def test_error_metrics_over_resolved_forecasts():
    """Two resolved forecasts: ₹500 high and ₹300 low."""
    report = forecast_evaluator.evaluate(pd.DataFrame([
        {"forecast_price": 5500.0, "actual_price": 5000.0},
        {"forecast_price": 4700.0, "actual_price": 5000.0},
    ]))
    assert report["mae"] == 400.0                              # (500 + 300) / 2
    assert report["mean_error"] == 100.0                       # (+500 - 300) / 2, signed
    assert report["median_absolute_error"] == 400.0
    assert report["rmse"] == math.sqrt((500.0 ** 2 + 300.0 ** 2) / 2)
    assert report["mape"] == 8.0                               # (10% + 6%) / 2
    assert report["sample_count"] == 2
    assert report["excluded_rows"] == 0


def test_mape_divides_by_the_fare_that_was_paid():
    """Not by `max(actual, 1.0)`.

    The evaluator computed `abs_error / np.maximum(actual, 1.0)`, so a row whose
    realised fare was non-positive was not skipped — it was scored against ₹1,
    producing a percentage of a fare nobody paid. A percentage error against a
    non-positive actual is undefined, so the row is excluded and counted.
    """
    report = forecast_evaluator.evaluate(pd.DataFrame([
        {"forecast_price": 5500.0, "actual_price": 5000.0},
        {"forecast_price": 5500.0, "actual_price": 0.0},
    ]))
    assert report["mape"] == 10.0            # the one positive actual; not 275_010.0
    assert report["mae"] == 3000.0           # MAE still uses both rows


def test_no_usable_outcome_is_undefined_not_zero():
    report = forecast_evaluator.evaluate(pd.DataFrame([]))
    for key in m.METRIC_KEYS:
        assert math.isnan(report[key]), f"{key} is {report[key]}, not NaN"
    assert report["sample_count"] == 0
    assert report["mae"] != 0.0


def test_unreadable_fares_are_excluded_and_counted():
    """Rather than dropped silently by pandas' own `.mean()`."""
    report = forecast_evaluator.evaluate(pd.DataFrame([
        {"forecast_price": 5500.0, "actual_price": 5000.0},
        {"forecast_price": None, "actual_price": 5000.0},
        {"forecast_price": "unavailable", "actual_price": 5000.0},
    ]))
    assert report["sample_count"] == 1
    assert report["excluded_rows"] == 2
    assert report["mae"] == 500.0


def test_grouped_accuracy_is_per_group():
    grouped = forecast_evaluator.evaluate_grouped(pd.DataFrame([
        {"route": "DEL-BOM", "forecast_price": 5500.0, "actual_price": 5000.0},
        {"route": "DEL-BOM", "forecast_price": 4900.0, "actual_price": 5000.0},
        {"route": "BLR-DEL", "forecast_price": 8000.0, "actual_price": 8000.0},
    ]), "route")
    assert set(grouped) == {"DEL-BOM", "BLR-DEL"}
    assert grouped["DEL-BOM"]["mae"] == 300.0
    assert grouped["DEL-BOM"]["sample_count"] == 2
    assert grouped["BLR-DEL"]["mae"] == 0.0


def test_the_removed_recommendation_metrics_are_not_back():
    """`recommendation_accuracy` counted `MONITOR` as automatically correct.

    A recommender that always said `MONITOR` therefore scored 100%. It also needs
    the fare quoted when the advice was given, which no column on a resolved
    forecast carries, so it cannot be recomputed from this frame at all.
    """
    report = forecast_evaluator.evaluate(pd.DataFrame([
        {"forecast_price": 5500.0, "actual_price": 5000.0},
    ]))
    for gone in ("recommendation_accuracy", "average_savings", "average_loss", "bias", "drift"):
        assert gone not in report
