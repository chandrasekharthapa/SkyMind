"""Tests for pure metric functions in metrics.py."""
import math
import numpy as np
import pytest
from backend.ml import metrics as m


Y_TRUE = np.array([100.0, 200.0, 150.0, 300.0, 250.0])
Y_PRED = np.array([110.0, 190.0, 160.0, 280.0, 260.0])


def test_mae_correct():
    result = m.mae(Y_TRUE, Y_PRED)
    expected = np.mean(np.abs(Y_TRUE - Y_PRED))
    assert abs(result - expected) < 1e-9


def test_rmse_correct():
    result = m.rmse(Y_TRUE, Y_PRED)
    expected = float(np.sqrt(np.mean((Y_TRUE - Y_PRED) ** 2)))
    assert abs(result - expected) < 1e-9


def test_mape_correct():
    result = m.mape(Y_TRUE, Y_PRED)
    assert result >= 0.0


def test_r2_perfect_prediction():
    result = m.r2(Y_TRUE, Y_TRUE)
    assert abs(result - 1.0) < 1e-9


def test_r2_constant_prediction():
    # Constant prediction at mean should give R² ≈ 0
    const = np.full_like(Y_TRUE, np.mean(Y_TRUE))
    result = m.r2(Y_TRUE, const)
    assert abs(result) < 1e-9


def test_mean_error_sign():
    # Predictions are mostly over-estimating
    result = m.mean_error(Y_TRUE, Y_PRED + 50)
    assert result > 0


def test_median_absolute_error():
    result = m.median_absolute_error(Y_TRUE, Y_PRED)
    assert result >= 0


def test_direction_accuracy_range():
    result = m.direction_accuracy(Y_TRUE, Y_PRED)
    assert 0.0 <= result <= 1.0


def test_direction_accuracy_returns_nan_for_single_value():
    result = m.direction_accuracy(np.array([100.0]), np.array([110.0]))
    assert math.isnan(result)


def test_compute_all_keys():
    result = m.compute_all(Y_TRUE, Y_PRED)
    required_keys = {"mae", "rmse", "mape", "r2", "mean_error", "median_absolute_error", "direction_accuracy"}
    assert required_keys.issubset(result.keys())
