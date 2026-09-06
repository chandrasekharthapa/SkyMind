"""Evaluation Report.

Aggregates model predictions against true values into a structured report.
Uses the pure functions from metrics.py — no inline metric computation here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

from backend.ml import metrics as m

logger = logging.getLogger(__name__)


@dataclass
class EvaluationReport:
    """Complete evaluation output for one training run."""

    forecast_horizon: int
    prediction_count: int
    feature_set_version: str
    evaluation_timestamp: str
    summary_metrics: Dict[str, float]       # mae, rmse, mape, r2, mean_error, median_ae, direction_accuracy
    fold_metrics: List[Dict[str, float]] = field(default_factory=list)   # per CV fold
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class ModelEvaluator:
    """Produces EvaluationReport from predictions and actuals.

    Accepts numpy arrays, pandas Series, or lists.
    """

    def evaluate(
        self,
        y_true,
        y_pred,
        *,
        forecast_horizon: int,
        feature_set_version: str,
        fold_metrics: Optional[List[Dict[str, float]]] = None,
    ) -> EvaluationReport:
        """Compute metrics and return a structured EvaluationReport.

        Args:
            y_true: Ground-truth prices.
            y_pred: Predicted prices.
            forecast_horizon: Horizon in days this model targets.
            feature_set_version: Feature set identifier.
            fold_metrics: Optional list of per-fold metric dicts from CV.

        Returns:
            EvaluationReport
        """
        y_true_arr = np.asarray(y_true, dtype=float)
        y_pred_arr = np.asarray(y_pred, dtype=float)

        mask = ~(np.isnan(y_true_arr) | np.isnan(y_pred_arr))
        y_true_clean = y_true_arr[mask]
        y_pred_clean = y_pred_arr[mask]

        if len(y_true_clean) == 0:
            # Was `{k: 0.0 for k in [...]}`, logged as "returning zero metrics".
            #
            # A zeroed block is not a description of a model that could not be
            # evaluated. MAE, RMSE and MAPE of 0.0 describe a *perfect*
            # forecaster, and R² of 0.0 is exactly the acceptance threshold —
            # `price_model.MIN_TEST_R2` is 0.0 and the gate compares `r2 >=
            # MIN_TEST_R2` — so a horizon whose evaluation set was entirely NaN
            # published flawless errors and passed the gate that exists to reject
            # models like it.
            #
            # NaN is what `backend.ml.metrics` already uses for a figure that is
            # undefined rather than large or small (see `mape_with_coverage`), and
            # it makes the existing gate fail closed without the gate needing to
            # know about this case: `math.isfinite(nan)` is False.
            logger.warning(
                "[ModelEvaluator] no usable (actual, predicted) pair among %d row(s) — "
                "every metric is undefined (NaN), not zero; this cannot pass acceptance.",
                len(y_true_arr),
            )
            summary = m.undefined_metrics()
        else:
            summary = m.compute_all(y_true_clean, y_pred_clean)

        logger.info(
            f"[ModelEvaluator] horizon={forecast_horizon}d  "
            f"n={len(y_true_clean)}  "
            f"MAE={summary.get('mae', 0):.2f}  "
            f"RMSE={summary.get('rmse', 0):.2f}  "
            f"R²={summary.get('r2', 0):.4f}"
        )

        return EvaluationReport(
            forecast_horizon=forecast_horizon,
            prediction_count=int(len(y_true_clean)),
            feature_set_version=feature_set_version,
            evaluation_timestamp=datetime.now(timezone.utc).isoformat(),
            summary_metrics=summary,
            fold_metrics=fold_metrics or [],
        )


model_evaluator = ModelEvaluator()
