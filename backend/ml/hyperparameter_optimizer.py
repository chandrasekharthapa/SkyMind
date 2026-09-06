"""Hyperparameter Optimizer.

Wraps Optuna for XGBoost hyperparameter search.

Optuna is a soft dependency:
  - If installed: runs a proper TPE-based search.
  - If not installed: returns default hyperparameters and logs a warning.

Optimization is always optional. Training continues normally either way.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import optuna as _optuna
    _optuna.logging.set_verbosity(_optuna.logging.WARNING)
    _OPTUNA_AVAILABLE = True
except ImportError:
    _optuna = None  # type: ignore[assignment]
    _OPTUNA_AVAILABLE = False


_DEFAULT_PARAMS: Dict[str, Any] = {
    "n_estimators": 900,
    "learning_rate": 0.04,
    "max_depth": 9,
    "min_child_weight": 1,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "gamma": 0.0,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
}


@dataclass
class OptimizationResult:
    """Result of one hyperparameter optimization run."""

    best_params: Dict[str, Any]
    best_val_mae: float
    n_trials_completed: int
    optuna_available: bool
    history: List[Dict[str, Any]] = field(default_factory=list)  # per-trial records

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class HyperparameterOptimizer:
    """Optuna-based hyperparameter optimizer for XGBoost models.

    Falls back to default params when Optuna is unavailable.
    Optimization is always optional — ModelTrainer passes optimize=False
    by default to keep training fast.
    """

    def optimize(
        self,
        X_train,                      # pd.DataFrame
        y_train,                      # pd.Series
        X_val,                        # pd.DataFrame
        y_val,                        # pd.Series
        *,
        n_trials: int = 50,
        random_seed: int = 42,
        output_dir: Optional[str] = None,
    ) -> OptimizationResult:
        """Run hyperparameter search and return the best parameters.

        Args:
            X_train: Training features.
            y_train: Training targets.
            X_val: Validation features.
            y_val: Validation targets.
            n_trials: Number of Optuna trials.
            random_seed: Used for reproducibility in XGBoost.
            output_dir: If provided, persists best_params.json and history.json.

        Returns:
            OptimizationResult
        """
        if not _OPTUNA_AVAILABLE:
            logger.warning(
                "[HyperparameterOptimizer] Optuna is not installed. "
                "Returning default hyperparameters. "
                "Install with: pip install optuna"
            )
            return OptimizationResult(
                best_params=dict(_DEFAULT_PARAMS),
                best_val_mae=float("nan"),
                n_trials_completed=0,
                optuna_available=False,
            )

        from xgboost import XGBRegressor
        from sklearn.metrics import mean_absolute_error

        history: List[Dict[str, Any]] = []

        def objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 200, 1200),
                "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
                "max_depth": trial.suggest_int("max_depth", 3, 12),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 1.0),
                "gamma": trial.suggest_float("gamma", 0.0, 5.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 5.0),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 5.0),
                "objective": "reg:squarederror",
                "random_state": random_seed,
            }

            model = XGBRegressor(**params)
            model.fit(X_train, y_train, verbose=False)
            preds = model.predict(X_val)
            trial_mae = mean_absolute_error(y_val, preds)
            history.append({"trial": trial.number, "mae": float(trial_mae), "params": params})
            return trial_mae

        sampler = _optuna.samplers.TPESampler(seed=random_seed)
        study = _optuna.create_study(direction="minimize", sampler=sampler)
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best_params = {**study.best_params, "objective": "reg:squarederror"}
        best_mae = float(study.best_value)

        logger.info(
            f"[HyperparameterOptimizer] Completed {n_trials} trials. "
            f"Best MAE={best_mae:.2f} with params={best_params}"
        )

        result = OptimizationResult(
            best_params=best_params,
            best_val_mae=best_mae,
            n_trials_completed=n_trials,
            optuna_available=True,
            history=history,
        )

        # ── Persist ──────────────────────────────────────────────────────────
        if output_dir:
            try:
                os.makedirs(output_dir, exist_ok=True)
                params_path = os.path.join(output_dir, "best_params.json")
                history_path = os.path.join(output_dir, "optimization_history.json")
                with open(params_path, "w") as f:
                    json.dump(best_params, f, indent=2)
                with open(history_path, "w") as f:
                    json.dump(history, f, indent=2)
                logger.info(f"[HyperparameterOptimizer] Persisted to {output_dir}")
            except Exception as e:
                logger.warning(f"[HyperparameterOptimizer] Failed to persist: {e}")

        return result


hyperparameter_optimizer = HyperparameterOptimizer()
