"""Training Result.

Immutable record of a completed training run.
Persisted alongside model artifacts for full auditability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class TrainingResult:
    """Complete record of a single model training run."""

    model_id: str                         # unique run identifier
    forecast_horizon: int                 # days ahead (1, 3, 7 …)
    feature_set_version: str             # "legacy" | "feature_set_v1"
    dataset_hash: str                    # SHA256 of engineered training DataFrame
    dataset_version: str                 # human-readable label e.g. "DS_20260720_123456"
    training_rows: int
    validation_rows: int
    metrics: Dict[str, float]            # mae, rmse, mape, r2, mean_error, median_ae, direction_accuracy
    training_duration_seconds: float
    training_timestamp: str              # ISO-8601 UTC
    git_commit: Optional[str] = None     # None when git is unavailable
    config_hash: Optional[str] = None   # hash of TrainingConfig used
    cv_metrics: Dict[str, Any] = field(default_factory=dict)   # cross-validation fold results

    # ──────────────────────────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def make_model_id(horizon: int, timestamp: Optional[str] = None) -> str:
        ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"model_h{horizon}d_{ts}"
