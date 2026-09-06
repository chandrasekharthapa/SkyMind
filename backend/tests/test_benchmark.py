"""Tests for ModelBenchmark and BenchmarkResult.

The contract these lock is that a baseline must be *supplied*, because the two
baselines this module used to compute for itself both read the test labels:
`naive_persistence` was the mean of `y_true`, and `rolling_mean_3` was a centred
convolution over `y_true` that reads `y[i+1]`. See the module docstring in
`backend/ml/benchmark.py` for why each one had to go.
"""
import json

import numpy as np
import pytest

from backend.ml.benchmark import ModelBenchmark, BenchmarkResult


# A fare that was on the screen, and what it turned out to be. Every fare rose by
# exactly 20, so the persistence baseline's MAE is 20.0 and can be checked by eye.
LAST = np.array([100.0, 200.0, 150.0, 300.0, 250.0] * 20)
Y_TRUE = LAST + 20.0
N = len(Y_TRUE)


def _run(y_pred, **kw):
    return ModelBenchmark().run(Y_TRUE, y_pred, **kw)


def _full(y_pred):
    """A run with every baseline input supplied."""
    return _run(y_pred, y_last_known=LAST, y_train=Y_TRUE - 100.0)


def test_benchmark_result_has_required_fields():
    result = _full(Y_TRUE + 5.0)
    assert isinstance(result, BenchmarkResult)
    assert result.verdict in ("improved", "unchanged", "regressed", "not_compared")
    assert isinstance(result.new_model_metrics, dict)
    assert len(result.baselines) > 0
    assert result.rows_scored == N


def test_a_run_with_no_baseline_says_so_instead_of_reporting_parity():
    """The headline fix: "we never compared" no longer prints as "unchanged".

    With no baseline input at all the old module appended nothing, fell through
    the verdict loop with `best_baseline_val = None`, and returned
    `verdict="unchanged", improvement_pct=0.0` — the same output as a model that
    had been measured against a baseline and matched it.
    """
    result = _run(Y_TRUE + 5.0)
    assert result.verdict == "not_compared"
    assert result.was_compared is False
    assert result.baselines == []
    assert result.best_baseline is None
    assert result.best_baseline_value is None
    assert result.notes
    # Every absent baseline is a recorded fact with a reason, not a gap in a list.
    assert {s.name for s in result.skipped_baselines} == {
        "persistence", "train_mean", "previous_production"}
    assert all(s.reason for s in result.skipped_baselines)


def test_persistence_is_the_supplied_last_known_fare_not_the_test_mean():
    result = _full(Y_TRUE + 5.0)
    persistence = next(b for b in result.baselines if b.name == "persistence")
    # Every fare rose by 20, so carrying the last-known fare forward is off by 20.
    assert persistence.metrics["mae"] == pytest.approx(20.0)
    assert persistence.metrics["mae"] == pytest.approx(
        float(np.mean(np.abs(Y_TRUE - LAST))))


def test_the_two_baselines_that_read_the_test_labels_are_gone():
    result = _full(Y_TRUE + 5.0)
    names = {b.name for b in result.baselines}
    assert "naive_persistence" not in names
    assert "rolling_mean_3" not in names
    assert names == {"persistence", "train_mean"}


def test_the_train_mean_baseline_is_not_the_mean_of_the_test_labels():
    """Which is what makes it an independent check rather than a restatement of R².

    A constant equal to `mean(y_true)` has R² identically 0.0, because R²'s
    denominator *is* the variance about `mean(y_true)`. The old baseline was
    exactly that constant, so it duplicated `price_model.MIN_TEST_R2 = 0.0`
    rather than adding anything. Taken from the training fold it is a real
    baseline that can be arbitrarily wrong.
    """
    result = _full(Y_TRUE + 5.0)
    train_mean = next(b for b in result.baselines if b.name == "train_mean")
    assert train_mean.metrics["r2"] < 0.0, (
        "a constant from the training fold has no reason to score R²=0 on the "
        "test fold; scoring exactly 0.0 would mean it was the test mean"
    )
    # It predicts mean(y_train) = mean(Y_TRUE) - 100, so it is low by 100.
    assert train_mean.metrics["mae"] == pytest.approx(100.0)
    assert "120.00" in train_mean.description


def test_a_centred_rolling_mean_would_have_failed_an_honest_model():
    """Why deleting `rolling_mean_3` was a fix and not a loosening.

    `np.convolve(y, ones(3)/3, mode="same")` is centred: its prediction for row i
    averages y[i-1], y[i] and y[i+1]. On a fare series smooth enough to be worth
    forecasting it is therefore near-exact, holds the lowest error of any
    baseline, becomes `best_baseline`, and drives every real model to
    "regressed". This test builds that situation and shows the surviving
    baselines grade the same model "improved".
    """
    n = 400
    last = np.linspace(4000.0, 6000.0, n)
    y_true = last + 50.0                      # a smooth ramp: fares drift up
    signs = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    y_pred = y_true + 25.0 * signs            # a real model: MAE exactly 25

    old_oracle = np.convolve(y_true, np.ones(3) / 3.0, mode="same")
    old_oracle_mae = float(np.mean(np.abs(y_true - old_oracle)))
    model_mae = float(np.mean(np.abs(y_true - y_pred)))
    assert old_oracle_mae < model_mae, (
        "fixture is not demonstrating the problem: the centred oracle must beat "
        "the model for its removal to matter"
    )

    result = ModelBenchmark().run(
        y_true, y_pred, y_last_known=last, y_train=y_true - 10.0)
    assert result.verdict == "improved"
    # Persistence is the bar the model genuinely clears: 25 against 50. On a
    # ramp this wide a single constant is far worse, so it is not the bar.
    assert result.best_baseline == "persistence"
    persistence = next(b for b in result.baselines if b.name == "persistence")
    assert persistence.metrics["mae"] == pytest.approx(50.0)
    assert result.best_baseline_value == pytest.approx(50.0)


def test_benchmark_improved_when_much_better():
    result = _full(Y_TRUE + 1.0)
    assert result.verdict == "improved"
    assert result.improvement_pct > 0.0


def test_benchmark_unchanged_when_the_model_only_repeats_the_last_known_fare():
    """A model with no skill over the price already on the screen.

    This is the comparison the old baseline set could not make, and the one that
    matters most for this project: `price` is a model feature, so a fit that has
    learned little beyond "repeat the input" still posts a respectable MAE.
    """
    result = _full(LAST.copy())
    assert result.verdict == "unchanged"
    assert result.best_baseline == "persistence"
    assert result.best_baseline_value == pytest.approx(20.0)


def test_benchmark_regressed_when_much_worse():
    result = _full(np.full_like(Y_TRUE, 0.0))
    assert result.verdict == "regressed"
    assert result.is_regression is True
    assert result.improvement_pct < 0.0


def test_benchmark_verdict_property():
    result = _full(Y_TRUE + 5.0)
    assert isinstance(result.is_regression, bool)
    assert isinstance(result.is_improvement, bool)
    assert isinstance(result.was_compared, bool)


def test_benchmark_all_metrics_present():
    result = _full(Y_TRUE + 10.0)
    for key in ("mae", "rmse", "mape", "r2"):
        assert key in result.new_model_metrics, f"Missing metric: {key}"


def test_benchmark_production_comparison():
    result = _full(Y_TRUE + 5.0)
    assert not any(b.name == "previous_production" for b in result.baselines)
    result = _run(Y_TRUE + 5.0, y_last_known=LAST, y_pred_production=Y_TRUE + 50.0)
    assert any(b.name == "previous_production" for b in result.baselines)


def test_a_production_prediction_of_the_wrong_length_is_skipped_not_raised():
    """The `[mask]`-before-length-check ordering used to crash the training run.

    `np.asarray(y_pred_production)[mask]` with a mask longer than the array
    raises IndexError, so the length guard on the following line was unreachable
    for exactly the case it was written for. One unusable baseline took down the
    whole run.
    """
    result = _run(Y_TRUE + 5.0, y_last_known=LAST,
                  y_pred_production=np.zeros(N - 40))
    skipped = {s.name: s.reason for s in result.skipped_baselines}
    assert "previous_production" in skipped
    assert str(N - 40) in skipped["previous_production"]
    assert str(N) in skipped["previous_production"]
    # The run still produced a verdict off the baseline that was usable.
    assert result.best_baseline == "persistence"


def test_a_last_known_price_with_holes_is_skipped_rather_than_scored_on_a_subset():
    """An error over a different row set is not comparable to the model's."""
    holed = LAST.copy()
    holed[3] = np.nan
    result = _run(Y_TRUE + 5.0, y_last_known=holed, y_train=Y_TRUE - 100.0)
    assert not any(b.name == "persistence" for b in result.baselines)
    reason = next(s.reason for s in result.skipped_baselines
                  if s.name == "persistence")
    assert f"1 of {N}" in reason


def test_nan_actuals_are_dropped_from_every_side_of_the_comparison():
    y_true = Y_TRUE.copy()
    y_true[:10] = np.nan
    result = ModelBenchmark().run(
        y_true, Y_TRUE + 5.0, y_last_known=LAST, y_pred_production=Y_TRUE + 50.0)
    assert result.rows_scored == N - 10
    for baseline in result.baselines:
        assert np.isfinite(baseline.metrics["mae"])
    # Persistence is still exactly 20 off, measured over the surviving rows only.
    persistence = next(b for b in result.baselines if b.name == "persistence")
    assert persistence.metrics["mae"] == pytest.approx(20.0)


def test_an_empty_fold_is_not_compared_and_does_not_raise():
    empty = np.array([], dtype=float)
    result = ModelBenchmark().run(empty, empty, y_last_known=empty, y_train=Y_TRUE)
    assert result.verdict == "not_compared"
    assert result.rows_scored == 0
    assert np.isnan(result.new_model_metrics["mae"])


def test_the_hardest_baseline_wins_for_a_higher_is_better_metric():
    """`r2` and `direction_accuracy` invert the comparison.

    Taking the numerically smallest value as "best" would have made the weakest
    baseline the bar for these two metrics.
    """
    result = ModelBenchmark().run(
        Y_TRUE, Y_TRUE + 1.0, y_last_known=LAST, y_train=Y_TRUE - 100.0,
        primary_metric="r2")
    values = {b.name: b.metrics["r2"] for b in result.baselines}
    assert result.best_baseline_value == pytest.approx(max(values.values()))
    assert result.verdict == "improved"


def test_a_non_finite_baseline_metric_cannot_win_the_comparison():
    """MAPE is NaN over a fold with no positive actual, and `NaN < x` is False.

    A NaN would have been picked up as `best_baseline_val` on the first
    iteration and then never displaced, silently deciding the verdict.
    """
    zeros = np.zeros(60)
    result = ModelBenchmark().run(
        zeros, zeros + 1.0, y_last_known=zeros, y_train=zeros,
        primary_metric="mape")
    assert result.verdict == "not_compared"
    assert result.best_baseline is None
    assert "finite" in result.notes


def test_benchmark_to_dict_is_serialisable_including_the_skips():
    result = _run(Y_TRUE + 5.0, y_last_known=LAST)
    d = result.to_dict()
    for key in ("verdict", "new_model_metrics", "baselines", "skipped_baselines",
                "best_baseline", "best_baseline_value", "rows_scored",
                "feature_set_version"):
        assert key in d
    json.dumps(d)   # the training report writes this to disk
    assert d["skipped_baselines"][0]["reason"]
