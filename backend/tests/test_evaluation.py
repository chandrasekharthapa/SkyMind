"""Tests for EvaluationReport and ModelEvaluator."""
import numpy as np
from backend.ml import metrics as m
from backend.ml.evaluation import ModelEvaluator, EvaluationReport


Y_TRUE = np.array([100.0, 200.0, 150.0, 300.0, 250.0])
Y_PRED = np.array([110.0, 190.0, 160.0, 280.0, 260.0])


def test_evaluation_report_fields():
    evaluator = ModelEvaluator()
    report = evaluator.evaluate(
        Y_TRUE, Y_PRED,
        forecast_horizon=3,
        feature_set_version="feature_set_v1",
    )
    assert isinstance(report, EvaluationReport)
    assert report.forecast_horizon == 3
    assert report.feature_set_version == "feature_set_v1"
    assert report.prediction_count == 5
    assert report.evaluation_timestamp is not None


def test_evaluation_report_required_metrics():
    evaluator = ModelEvaluator()
    report = evaluator.evaluate(
        Y_TRUE, Y_PRED,
        forecast_horizon=7,
        feature_set_version="feature_set_v1",
    )
    required = {"mae", "rmse", "mape", "r2", "mean_error", "median_absolute_error", "direction_accuracy"}
    assert required.issubset(report.summary_metrics.keys())


def test_evaluation_report_mae_positive():
    evaluator = ModelEvaluator()
    report = evaluator.evaluate(Y_TRUE, Y_PRED, forecast_horizon=1, feature_set_version="legacy")
    assert report.summary_metrics["mae"] > 0


def test_evaluation_report_all_nan_metrics_are_undefined_not_zero():
    """No usable pair means every metric is NaN, and the acceptance gate rejects it.

    This asserted `summary_metrics["mae"] == 0.0`, ratifying a zeroed block as the
    answer for a model that could not be evaluated at all. Zero MAE, RMSE and MAPE
    describe a perfect forecaster, and R² 0.0 is exactly `MIN_TEST_R2`, which the
    gate compares with `>=` — so the unevaluable case published flawless errors
    and passed.
    """
    import math

    evaluator = ModelEvaluator()
    report = evaluator.evaluate(
        np.array([np.nan, np.nan]),
        np.array([1.0, 2.0]),
        forecast_horizon=3,
        feature_set_version="feature_set_v1",
    )
    assert report.prediction_count == 0
    for key in m.METRIC_KEYS:
        assert math.isnan(report.summary_metrics[key]), f"{key} is not NaN"

    # `price_model.evaluate_acceptance` admits a horizon on
    # `math.isfinite(r2) and r2 >= MIN_TEST_R2`. The first half is what rejects
    # this case, whatever the threshold is set to. Asserted here rather than
    # imported so that this module stays free of the xgboost/sklearn stack.
    assert not math.isfinite(report.summary_metrics["r2"])


def test_evaluation_report_to_dict():
    evaluator = ModelEvaluator()
    report = evaluator.evaluate(Y_TRUE, Y_PRED, forecast_horizon=3, feature_set_version="feature_set_v1")
    d = report.to_dict()
    assert "summary_metrics" in d
    assert "forecast_horizon" in d


def test_evaluation_report_fold_metrics_passthrough():
    evaluator = ModelEvaluator()
    folds = [{"mae": 100.0, "fold": 1.0}, {"mae": 90.0, "fold": 2.0}]
    report = evaluator.evaluate(
        Y_TRUE, Y_PRED,
        forecast_horizon=3,
        feature_set_version="feature_set_v1",
        fold_metrics=folds,
    )
    assert len(report.fold_metrics) == 2
