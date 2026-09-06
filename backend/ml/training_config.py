"""Training Configuration.

Immutable configuration for a single model training run.
Every field that affects reproducibility is captured here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Literal


ValidationStrategy = Literal["expanding", "rolling", "holdout"]
ModelType = Literal["xgboost"]


@dataclass(frozen=True)
class TrainingConfig:
    """Immutable configuration for one training run.

    Identical config + identical dataset → reproducible results.
    """

    feature_set_version: str                          # "legacy" | "feature_set_v1"
    forecast_horizon: int                              # days ahead, e.g. 1, 3, 7
    model_type: ModelType = "xgboost"
    random_seed: int = 42
    validation_strategy: ValidationStrategy = "expanding"
    minimum_training_rows: int = 50
    test_size: float = 0.2                            # holdout fraction (0–1)
    n_cv_folds: int = 5                               # folds for cross-validation
    hyperparameters: Dict[str, Any] = field(
        default_factory=lambda: {
            "n_estimators": 900,
            "learning_rate": 0.04,
            "max_depth": 9,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "min_child_weight": 1,
            "gamma": 0.0,
            "reg_alpha": 0.0,
            "reg_lambda": 1.0,
            "objective": "reg:squarederror",
        }
    )

    def config_hash(self) -> str:
        """Deterministic SHA256 of all config fields for audit trails."""
        d = {
            "feature_set_version": self.feature_set_version,
            "forecast_horizon": self.forecast_horizon,
            "model_type": self.model_type,
            "random_seed": self.random_seed,
            "validation_strategy": self.validation_strategy,
            "minimum_training_rows": self.minimum_training_rows,
            "test_size": self.test_size,
            "n_cv_folds": self.n_cv_folds,
            "hyperparameters": self.hyperparameters,
        }
        raw = json.dumps(d, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
