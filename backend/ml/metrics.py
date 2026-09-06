"""Evaluation Metrics — Pure Functions.

No side effects. No logging. No state.
All functions accept numpy arrays or pandas Series.
"""

from __future__ import annotations

import numpy as np
from typing import Union

Array = Union[np.ndarray, "pd.Series"]  # type: ignore[name-defined]


def _to_array(x: Array) -> np.ndarray:
    arr = np.asarray(x, dtype=float)
    return arr


def mae(y_true: Array, y_pred: Array) -> float:
    """Mean Absolute Error."""
    t, p = _to_array(y_true), _to_array(y_pred)
    return float(np.mean(np.abs(t - p)))


def rmse(y_true: Array, y_pred: Array) -> float:
    """Root Mean Squared Error."""
    t, p = _to_array(y_true), _to_array(y_pred)
    return float(np.sqrt(np.mean((t - p) ** 2)))


def mape_with_coverage(y_true: Array, y_pred: Array) -> tuple:
    """Return (MAPE %, rows used, rows excluded) over strictly positive actuals.

    The denominator used to be `np.maximum(np.abs(t), 1.0)`, described as avoiding
    division by zero. It does avoid it, by substituting 1.0 for the true value —
    which does not skip the row, it keeps it with a denominator that is wrong by
    however far the actual was from ₹1. Every such row's percentage error is
    computed against a fare nobody paid, and because the substituted denominator
    is the smallest one in the batch the effect on a fare-scale target is to make
    the error look *smaller* relative to the alternative of excluding it only when
    the model was close, and wildly larger when it was not. Either way the figure
    stops being a percentage of anything.

    A percentage error against a non-positive actual is undefined, so those rows
    are excluded and counted. Publishing the count alongside the figure is the
    point: a MAPE over 3 of 400 rows and a MAPE over 400 of 400 are different
    claims, and clipping made them look identical.

    Returns NaN when no row has a positive actual. NaN is deliberate — it is not
    a large error and not a small one, and a caller that treats it as either is
    the bug this signals. `MAX_TEST_MAPE`-style comparisons against NaN are False,
    so a gate reading this figure fails closed.
    """
    t, p = _to_array(y_true), _to_array(y_pred)
    usable = np.isfinite(t) & np.isfinite(p) & (t > 0.0)
    n_used = int(np.count_nonzero(usable))
    n_excluded = int(t.size - n_used)
    if n_used == 0:
        return float("nan"), 0, n_excluded
    err = np.abs(t[usable] - p[usable]) / t[usable]
    return float(np.mean(err) * 100.0), n_used, n_excluded


def mape(y_true: Array, y_pred: Array) -> float:
    """Mean Absolute Percentage Error (%), over positive actuals only.

    Thin wrapper over `mape_with_coverage` so that there is one definition of the
    metric. NaN when no actual is positive.
    """
    value, _, _ = mape_with_coverage(y_true, y_pred)
    return value


def r2(y_true: Array, y_pred: Array) -> float:
    """Coefficient of Determination (R²)."""
    t, p = _to_array(y_true), _to_array(y_pred)
    ss_res = np.sum((t - p) ** 2)
    ss_tot = np.sum((t - np.mean(t)) ** 2)
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return float(1.0 - ss_res / ss_tot)


def mean_error(y_true: Array, y_pred: Array) -> float:
    """Signed Mean Error (positive = over-prediction bias)."""
    t, p = _to_array(y_true), _to_array(y_pred)
    return float(np.mean(p - t))


def median_absolute_error(y_true: Array, y_pred: Array) -> float:
    """Median Absolute Error."""
    t, p = _to_array(y_true), _to_array(y_pred)
    return float(np.median(np.abs(t - p)))


def direction_accuracy(y_true: Array, y_pred: Array) -> float:
    """Fraction of predictions with the correct price direction vs mean.

    Computes whether the predicted price is on the correct side of the mean
    compared to the actual price (i.e., both above or both below the mean).
    Returns a value in [0, 1].
    """
    t, p = _to_array(y_true), _to_array(y_pred)
    if len(t) < 2:
        return float("nan")
    mean_t = np.mean(t)
    correct = np.sum(np.sign(t - mean_t) == np.sign(p - mean_t))
    return float(correct / len(t))


# One definition of "the metric set", because the same seven names were written
# out by hand in `evaluation.py`, `cross_validation.py` and two test modules, and
# a dict literal listing them a fifth time is how a key goes missing from one of
# the five. `compute_all` and `undefined_metrics` are both built from this
# mapping, so the keys and the functions behind them cannot drift apart.
_METRIC_FUNCS = {
    "mae": mae,
    "rmse": rmse,
    "mape": mape,
    "r2": r2,
    "mean_error": mean_error,
    "median_absolute_error": median_absolute_error,
    "direction_accuracy": direction_accuracy,
}

METRIC_KEYS: tuple = tuple(_METRIC_FUNCS)



def compute_all(y_true: Array, y_pred: Array) -> dict:
    """Compute all metrics and return as a dictionary."""
    return {name: fn(y_true, y_pred) for name, fn in _METRIC_FUNCS.items()}


def undefined_metrics() -> dict:
    """Every metric as NaN, for a set with no usable (actual, predicted) pair.

    Zero is the wrong answer to "how wrong was this model on nothing": MAE, RMSE
    and MAPE of 0.0 read as a *perfect* forecaster, and an R² of 0.0 is exactly
    the acceptance threshold `price_model.MIN_TEST_R2` compares against with
    `>=`. NaN says undefined, which is what it is, and gates fail closed on it
    because every comparison against NaN is False — the same reasoning
    `mape_with_coverage` documents above.
    """
    return {name: float("nan") for name in METRIC_KEYS}

