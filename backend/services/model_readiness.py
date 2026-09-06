"""Model Readiness Module (Milestone 5).

Evaluates observation counts, minimum rows per horizon, feature completeness,
training eligibility, dataset version, and feature_set_version.
Returns READY or NOT_READY with detailed reasons.
"""

import logging
from typing import Any, Dict, List
from backend.database.database import database as db
from backend.services.model_registry import model_registry

logger = logging.getLogger(__name__)


class ModelReadinessService:
    def __init__(self, min_observations_threshold: int = 100):
        self.min_observations_threshold = min_observations_threshold

    def check_readiness(self) -> Dict[str, Any]:
        """Perform a complete model readiness evaluation."""
        reasons = []

        # 1. Fetch training dataset
        df_raw = db.get_training_dataset()
        total_obs = len(df_raw) if df_raw is not None else 0

        if total_obs < self.min_observations_threshold:
            reasons.append(f"Insufficient total observations ({total_obs} < {self.min_observations_threshold})")

        # 2. Check feature completeness
        completeness = 1.0
        if df_raw is not None and not df_raw.empty:
            total_cells = df_raw.shape[0] * df_raw.shape[1]
            non_nulls = df_raw.notna().sum().sum()
            completeness = float(non_nulls / max(1, total_cells))

            if completeness < 0.70:
                reasons.append(f"Low dataset feature completeness ({completeness*100:.1f}% < 70.0%)")

        # 3. Read the active model's versions off the registry.
        #
        # These were `getattr(model_registry, "feature_set_version", "legacy")` and
        # `getattr(model_registry, "model_version", "2.0.0")`. Both attributes are
        # properties that exist, so neither default could fire — but the defaults
        # were the readiness report's answer of record for "we do not know", and
        # they answered it with two invented version strings. The properties
        # themselves now return None when nothing records a version, and this
        # report passes that through instead of dressing it as a version.
        fs_version = model_registry.feature_set_version
        model_version = model_registry.model_version

        # 4. Check active horizon model files on disk
        from backend.ml.price_model import PricePredictor
        predictor = PricePredictor()
        # `load()` raises FileNotFoundError when the models directory holds
        # nothing, so the unguarded call meant this readiness check could not
        # report the one condition the next three lines were written to report:
        # it raised out of the endpoint instead of answering NOT_READY. A
        # readiness probe that throws is the least useful kind.
        try:
            predictor.load()
        except FileNotFoundError as exc:
            reasons.append(f"No model artifact on disk ({exc})")

        horizons_trained = list(predictor.models.keys())
        if not horizons_trained and not any(r.startswith("No model artifact") for r in reasons):
            reasons.append("No active horizon models trained or loaded from disk")

        # A present-but-refused artifact is a different state from an absent one,
        # and the reason is the whole point: since the leak audit, `load()`
        # declines any artifact whose metadata does not record a clean one. Naming
        # the refusals here is how an operator finds out why a directory full of
        # .pkl files still reports NOT_READY.
        refused = list(getattr(predictor, "refused_artifacts", []) or [])
        for item in refused:
            reasons.append(f"Refused artifact — {item}")

        is_ready = len(reasons) == 0
        status = "READY" if is_ready else "NOT_READY"

        return {
            "status": status,
            "is_ready": is_ready,
            "reasons": reasons,
            "total_observations": total_obs,
            "minimum_required_observations": self.min_observations_threshold,
            "feature_completeness_ratio": round(completeness, 4),
            # `str(...)` used to wrap both of these. With the invented defaults
            # gone, that would publish the string "None" — a version-shaped value
            # for the absence of one — so an absent version stays null.
            "feature_set_version": str(fs_version) if fs_version else None,
            "model_version": str(model_version) if model_version else None,
            "horizons_trained": horizons_trained,
            "refused_artifacts": refused
        }


model_readiness_service = ModelReadinessService()
