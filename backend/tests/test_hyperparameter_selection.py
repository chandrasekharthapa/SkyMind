"""select_hyperparameters: Optuna tuning on the training fold only, adopted only
when it beats the defaults on a time-ordered validation slice."""
import numpy as np
import pandas as pd
import pytest

import backend.ml.hyperparameter_optimizer as hpo
from backend.ml.price_model import (
    DEFAULT_HYPERPARAMETERS, TRAINING_OBJECTIVE, sample_weights_for, select_hyperparameters, tuning_settings,
)

FEATURES = ["days_to_departure", "weekday", "noise"]


def _frame(n=600, seed=0):
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp("2026-09-01", tz="UTC")
    dtd = rng.integers(1, 60, n)
    weekday = rng.integers(0, 7, n)
    # The model learns the future fare as a multiple of the fare quoted now.
    price = rng.uniform(3500, 6500, n)
    ratio = 1.0 + 0.3 / (dtd + 1) + 0.03 * (weekday >= 5) + rng.normal(0, 0.01, n)
    return pd.DataFrame({
        "_recorded_dt": [t0 + pd.Timedelta(hours=2 * i) for i in range(n)],
        "days_to_departure": dtd,
        "weekday": weekday,
        "noise": rng.normal(0, 1, n),
        "price": price,
        "target_price": price * ratio,
        "training_weight": 1.0,
    })


def test_disabled_tuning_keeps_the_defaults():
    params, record = select_hyperparameters(
        _frame(), FEATURES, embargo_days=1.0, n_trials=0, timeout_s=10, min_fit_rows=100)
    assert params == DEFAULT_HYPERPARAMETERS
    assert record["chosen"] == "default" and "disabled" in record["reason"]


def test_missing_optuna_keeps_the_defaults(monkeypatch):
    monkeypatch.setattr(hpo, "_OPTUNA_AVAILABLE", False)
    params, record = select_hyperparameters(
        _frame(), FEATURES, embargo_days=1.0, n_trials=5, timeout_s=10, min_fit_rows=100)
    assert params == DEFAULT_HYPERPARAMETERS
    assert record["reason"] == "optuna is not installed"


def test_too_small_a_training_fold_keeps_the_defaults():
    params, record = select_hyperparameters(
        _frame(n=90), FEATURES, embargo_days=1.0, n_trials=5, timeout_s=10, min_fit_rows=100)
    assert params == DEFAULT_HYPERPARAMETERS
    assert "too small" in record["reason"]


def test_tuning_settings_read_the_environment(monkeypatch):
    monkeypatch.setenv("MODEL_TUNING_TRIALS", "7")
    monkeypatch.setenv("MODEL_TUNING_TIMEOUT_S", "30")
    assert tuning_settings() == {"n_trials": 7, "timeout_s": 30.0}
    monkeypatch.setenv("MODEL_TUNING_TRIALS", "not a number")
    assert tuning_settings()["n_trials"] == 25


def test_sample_weights_default_and_floor():
    df = pd.DataFrame({"training_weight": [2.0, None, -1.0]})
    assert sample_weights_for(df).tolist() == [2.0, 1.0, 0.01]
    assert sample_weights_for(pd.DataFrame({"x": [1, 2]})).tolist() == [1.0, 1.0]


@pytest.mark.skipif(not hpo._OPTUNA_AVAILABLE, reason="optuna not installed")
def test_optuna_search_runs_on_the_training_fold_and_is_recorded():
    df = _frame()
    params, record = select_hyperparameters(
        df, FEATURES, embargo_days=1.0, n_trials=6, timeout_s=60, min_fit_rows=100)
    assert record["method"] == "optuna_tpe"
    assert record["n_trials_completed"] >= 1
    # The validation slice is the tail of the frame it was given: tuning sees
    # nothing later than the training fold.
    assert pd.Timestamp(record["validation_split"]["test_start"]) <= df["_recorded_dt"].max()
    if record["chosen"] == "tuned":
        assert record["validation_mae_tuned"] < record["validation_mae_default"]
        assert params == record["tuned_params"] and params["random_state"] == 42
    else:
        assert params == DEFAULT_HYPERPARAMETERS
    assert record["tuned_params"]["objective"] == TRAINING_OBJECTIVE


def test_the_training_loss_is_the_one_the_gate_judges():
    """The gate compares mean absolute error with "the fare stays the same".

    When most fares do not move and the ones that do mostly rise, a squared-error
    fit predicts the mean ratio — above 1 almost everywhere — and adds error to
    every unchanged fare. An absolute-error fit predicts the median, which is the
    persistence forecast wherever no change is likeliest.
    """
    from xgboost import XGBRegressor
    assert DEFAULT_HYPERPARAMETERS["objective"] == TRAINING_OBJECTIVE == "reg:absoluteerror"
    rng = np.random.default_rng(1)

    def fares(n):
        dtd = rng.integers(1, 60, n)
        price = rng.uniform(3000, 9000, n)
        ratio = np.ones(n)
        up = rng.random(n) < 0.25
        ratio[up] = np.exp(rng.normal(0.15, 0.08, up.sum()))
        jump = rng.random(n) < 0.01
        ratio[jump] *= rng.uniform(2.5, 5.0, jump.sum())
        return pd.DataFrame({"days_to_departure": dtd, "weekday": rng.integers(0, 7, n)}), price, price * ratio

    X, p, y = fares(3000)
    Xt, pt, yt = fares(1000)
    persistence = np.mean(np.abs(yt - pt))
    params = dict(DEFAULT_HYPERPARAMETERS, n_estimators=200)
    absolute = XGBRegressor(**params).fit(X, y / p)
    squared = XGBRegressor(**dict(params, objective="reg:squarederror")).fit(X, y / p)
    mae_abs = np.mean(np.abs(yt - absolute.predict(Xt) * pt))
    mae_sq = np.mean(np.abs(yt - squared.predict(Xt) * pt))
    assert mae_abs <= persistence * 1.05
    assert mae_sq > persistence          # why the loss was changed
