"""Feature Importance.

Generates feature importance reports using:
  1. Native XGBoost importance types: gain, weight, cover
  2. SHAP values (global, local, interactions) if the shap package is installed

Reports are persisted alongside model artifacts.
SHAP is an optional soft dependency — absence is handled gracefully.
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
    import shap as _shap
    _SHAP_AVAILABLE = True
except ImportError:
    _shap = None  # type: ignore[assignment]
    _SHAP_AVAILABLE = False


@dataclass
class FeatureImportanceReport:
    """Feature importance data for one trained model."""

    horizon: int
    feature_set_version: str
    shap_available: bool = False

    # XGBoost native importance
    gain: Dict[str, float] = field(default_factory=dict)
    weight: Dict[str, float] = field(default_factory=dict)
    cover: Dict[str, float] = field(default_factory=dict)

    # SHAP (only populated if shap is installed)
    shap_global_mean_abs: Dict[str, float] = field(default_factory=dict)   # mean |SHAP| per feature
    shap_local_sample: Optional[Dict[str, float]] = None                    # single-row explanation
    shap_interaction_available: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def top_n_by_gain(self, n: int = 10) -> List[str]:
        """Return feature names ranked by gain (descending)."""
        return sorted(self.gain, key=lambda k: self.gain[k], reverse=True)[:n]


class FeatureImportanceAnalyzer:
    """Extracts and persists feature importance reports for XGBoost models."""

    def generate(
        self,
        model,                       # trained XGBRegressor
        feature_names: List[str],
        X_val,                       # pd.DataFrame — validation features (for SHAP)
        *,
        horizon: int,
        feature_set_version: str,
        importance_path: Optional[str] = None,
    ) -> FeatureImportanceReport:
        """Generate importance report and optionally persist it.

        Args:
            model: Fitted XGBRegressor.
            feature_names: Ordered list of feature names.
            X_val: Validation feature DataFrame (used for SHAP).
            horizon: Forecast horizon in days.
            feature_set_version: Feature set identifier.
            importance_path: If provided, write JSON to this path.

        Returns:
            FeatureImportanceReport
        """
        report = FeatureImportanceReport(
            horizon=horizon,
            feature_set_version=feature_set_version,
            shap_available=_SHAP_AVAILABLE,
        )

        # ── XGBoost native importance ────────────────────────────────────────
        for itype in ("gain", "weight", "cover"):
            try:
                raw = model.get_booster().get_score(importance_type=itype)
                # Map f0, f1 … back to feature names if XGBoost used positional naming
                named: Dict[str, float] = {}
                for k, v in raw.items():
                    if k.startswith("f") and k[1:].isdigit():
                        idx = int(k[1:])
                        fname = feature_names[idx] if idx < len(feature_names) else k
                    else:
                        fname = k
                    named[fname] = float(v)
                setattr(report, itype, named)
            except Exception as e:
                logger.warning(f"[FeatureImportance] Could not extract {itype}: {e}")

        # ── SHAP ─────────────────────────────────────────────────────────────
        if _SHAP_AVAILABLE and X_val is not None and len(X_val) > 0:
            try:
                import pandas as pd
                X_sample = X_val.head(min(100, len(X_val))) if hasattr(X_val, "head") else X_val[:100]

                explainer = _shap.TreeExplainer(model)
                shap_values = explainer.shap_values(X_sample)

                mean_abs = np.abs(shap_values).mean(axis=0)
                report.shap_global_mean_abs = {
                    fname: float(v) for fname, v in zip(feature_names, mean_abs)
                }

                # Local explanation for first sample
                if len(shap_values) > 0:
                    report.shap_local_sample = {
                        fname: float(v)
                        for fname, v in zip(feature_names, shap_values[0])
                    }

                # Interaction values (memory-intensive — only for small validation sets)
                if len(X_sample) <= 50:
                    try:
                        explainer.shap_interaction_values(X_sample)
                        report.shap_interaction_available = True
                    except Exception:
                        pass

                logger.info("[FeatureImportance] SHAP values computed successfully.")
            except Exception as e:
                logger.warning(f"[FeatureImportance] SHAP computation failed: {e}")

        # ── Persist ──────────────────────────────────────────────────────────
        if importance_path:
            try:
                os.makedirs(os.path.dirname(importance_path), exist_ok=True)
                with open(importance_path, "w") as fh:
                    fh.write(report.to_json())
                logger.info(f"[FeatureImportance] Persisted to {importance_path}")
            except Exception as e:
                logger.warning(f"[FeatureImportance] Failed to persist report: {e}")

        return report


feature_importance_analyzer = FeatureImportanceAnalyzer()
