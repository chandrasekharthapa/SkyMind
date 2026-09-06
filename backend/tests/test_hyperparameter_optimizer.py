"""Tests for HyperparameterOptimizer — Optuna wrapper with graceful fallback."""
import numpy as np
import pandas as pd

from backend.ml.hyperparameter_optimizer import HyperparameterOptimizer, OptimizationResult


def _make_data():
    rng = np.random.default_rng(42)
    n = 100
    X = pd.DataFrame({"f_a": rng.uniform(100, 500, n), "f_b": rng.uniform(0, 30, n)})
    y = pd.Series(X["f_a"] * 0.7 + X["f_b"] * 3 + rng.normal(0, 15, n))
    X_tr, X_vl = X.iloc[:80], X.iloc[80:]
    y_tr, y_vl = y.iloc[:80], y.iloc[80:]
    return X_tr, y_tr, X_vl, y_vl


def test_optimizer_returns_result():
    X_tr, y_tr, X_vl, y_vl = _make_data()
    opt = HyperparameterOptimizer()
    result = opt.optimize(X_tr, y_tr, X_vl, y_vl, n_trials=2, random_seed=42)
    assert isinstance(result, OptimizationResult)


def test_optimizer_best_params_non_empty():
    X_tr, y_tr, X_vl, y_vl = _make_data()
    opt = HyperparameterOptimizer()
    result = opt.optimize(X_tr, y_tr, X_vl, y_vl, n_trials=2, random_seed=42)
    assert isinstance(result.best_params, dict)
    assert len(result.best_params) > 0


def test_optimizer_fallback_when_optuna_unavailable(monkeypatch):
    """Simulate Optuna not being installed — should return defaults gracefully."""
    import backend.ml.hyperparameter_optimizer as mod
    original = mod._OPTUNA_AVAILABLE
    mod._OPTUNA_AVAILABLE = False
    try:
        X_tr, y_tr, X_vl, y_vl = _make_data()
        opt = HyperparameterOptimizer()
        result = opt.optimize(X_tr, y_tr, X_vl, y_vl)
        assert result.optuna_available is False
        assert result.n_trials_completed == 0
        assert "learning_rate" in result.best_params
    finally:
        mod._OPTUNA_AVAILABLE = original


def test_optimizer_params_contain_required_keys():
    X_tr, y_tr, X_vl, y_vl = _make_data()
    opt = HyperparameterOptimizer()
    result = opt.optimize(X_tr, y_tr, X_vl, y_vl, n_trials=2, random_seed=42)
    required = {"learning_rate", "max_depth", "subsample", "colsample_bytree"}
    assert required.issubset(result.best_params.keys())


def test_optimizer_persist(tmp_path):
    X_tr, y_tr, X_vl, y_vl = _make_data()
    opt = HyperparameterOptimizer()
    import os
    result = opt.optimize(X_tr, y_tr, X_vl, y_vl, n_trials=2, output_dir=str(tmp_path))
    # If optuna is available the files should be created
    if result.optuna_available:
        assert os.path.isfile(str(tmp_path / "best_params.json"))
