"""Feature Validation Module (Milestone 2).

Checks a feature vector or feature frame against `EXPECTED_FEATURE_COLS`: which
names are missing, which are unexpected, whether the leading columns appear in
the declared order, whether the identity columns are non-null, and what fraction
of cells are populated. Writes `feature_validation_report.json` into
`backend/reports/` — see `backend.utils.report_paths` for why it is no longer
written to the repository root.

This docstring used to say the module verifies "determinism" and "ownership" as
well. It verifies neither: nothing here builds features twice to compare, and no
column is attributed to a producer. The report's `determinism_verified` field said
`true` on every run for the same reason. See `validate_features_dataframe`.

`EXPECTED_FEATURE_COLS` used to be a third hand-copied version of the feature
contract, alongside the predictor's `feature_cols` and the parity test's list, and
could disagree with the model actually loaded. It is now derived from
`backend.ml.feature_metadata`, and `FeatureValidationService.expected_features`
resolves the *deployed* model's feature set at call time rather than assuming the
legacy one.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

from backend.ml.feature_metadata import FEATURE_SET_V1, LEGACY_FEATURE_SET
from backend.utils.report_paths import report_path, write_report


logger = logging.getLogger(__name__)

REPORT_PATH = report_path("feature_validation_report.json")

FEATURE_NAMES_BY_VERSION: Dict[str, List[str]] = {
    "legacy": [f.name for f in LEGACY_FEATURE_SET],
    "feature_set_v1": [f.name for f in FEATURE_SET_V1],
}

# The default when the deployed model cannot be consulted — not a copy of the
# contract, a selection from it.
EXPECTED_FEATURE_COLS = FEATURE_NAMES_BY_VERSION["legacy"]


class FeatureValidationService:
    @property
    def expected_features(self) -> List[str]:
        """The feature names the currently deployed model expects.

        This was `self.expected_features = EXPECTED_FEATURE_COLS`, fixed at import
        time to the legacy 16 whatever was loaded, so `production_readiness` graded
        a raw observations frame against a contract the running model might not
        hold. `model_registry.feature_set_version` is the same value
        `training_dataset_builder` and `prediction_service` build against, so
        reading it here makes all three agree by construction.

        The registry import is local: `model_registry` imports `price_model`, and
        `production_readiness` imports this module, so a module-level import puts a
        cycle one refactor away. A registry that cannot answer is a reason to fall
        back and say so, not to fail a readiness check — the check's own job is to
        report that state.
        """
        try:
            from backend.services.model_registry import model_registry
            version = model_registry.feature_set_version
        except Exception as exc:  # registry unavailable, no artifact loaded, cycle
            logger.warning(
                "Could not read the deployed feature-set version (%s: %s); "
                "validating against %r.", type(exc).__name__, exc, "legacy")
            return FEATURE_NAMES_BY_VERSION["legacy"]

        names = FEATURE_NAMES_BY_VERSION.get(version)
        if names is None:
            logger.warning(
                "Deployed model advertises unknown feature set %r; validating "
                "against %r instead. Known sets: %s.",
                version, "legacy", sorted(FEATURE_NAMES_BY_VERSION))
            return FEATURE_NAMES_BY_VERSION["legacy"]
        return names

    def validate_feature_vector(self, feature_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a single feature dictionary against schema rules."""
        missing = [f for f in self.expected_features if f not in feature_dict]
        extra = [f for f in feature_dict.keys() if f not in self.expected_features]
        
        # Check core identity features for unexpected NaN
        core_nans = []
        for core_col in ["origin_code", "destination_code", "is_live"]:
            val = feature_dict.get(core_col)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                core_nans.append(core_col)

        is_valid = len(missing) == 0 and len(core_nans) == 0

        return {
            "valid": is_valid,
            "feature_count": len(feature_dict),
            "missing_features": missing,
            "extra_features": extra,
            "core_identity_nans": core_nans
        }

    def validate_features_dataframe(
        self, df_features: pd.DataFrame, destination: Optional[str] = None
    ) -> Dict[str, Any]:
        """Check a features DataFrame for order, missing columns, and completeness.

        The summary line said "for determinism, order, NaN propagation, and
        completeness". Determinism is not among them and cannot be, from a frame
        that is already built; the report field that claimed it is now null with a
        reason attached.

        `destination` overrides where the report is written; it defaults to
        `REPORT_PATH`.
        """
        if df_features is None or df_features.empty:
            # This path used to return without writing anything, so on an empty
            # corpus the report file kept whatever a previous run had left there —
            # a stale PASS describing a frame that no longer existed. An empty
            # frame is a result, and it gets an artifact like any other.
            empty = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "valid": False,
                "total_rows": 0,
                "feature_count": 0,
                "expected_feature_count": len(self.expected_features),
                "missing_features": self.expected_features,
                "feature_completeness": 0.0,
                "reason": "DataFrame is empty or None"
            }
            write_report(empty, destination or REPORT_PATH)
            return empty

        cols = list(df_features.columns)
        missing = [f for f in self.expected_features if f not in cols]
        extra = [f for f in cols if f not in self.expected_features]
        
        # Compute feature completeness ratio
        total_cells = df_features.shape[0] * df_features.shape[1]
        non_null_cells = df_features.notna().sum().sum()
        completeness_ratio = float(non_null_cells / max(1, total_cells))

        is_valid = len(missing) == 0 and completeness_ratio >= 0.70

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "valid": is_valid,
            "total_rows": len(df_features),
            "feature_count": len(cols),
            "expected_feature_count": len(self.expected_features),
            "missing_features": missing,
            "extra_features": extra,
            "feature_ordering_matched": cols[:len(self.expected_features)] == self.expected_features,
            "feature_completeness": round(completeness_ratio, 4),
            # Was `"determinism_verified": True` — a literal in a field whose name
            # asserts that a check ran. Nothing here checks determinism, and this
            # method structurally cannot: it is handed a finished frame, so it has
            # no way to rebuild the features a second time and compare. The module
            # docstring made the same claim. The key is kept because
            # `production_readiness` copies this report into its own output
            # verbatim, but it now reports that the check did not run rather than
            # that it passed.
            "determinism_verified": None,
            "determinism_check": (
                "not performed: this method receives an already-built frame and "
                "cannot re-run feature construction to compare"
            ),
        }

        write_report(report, destination or REPORT_PATH)

        return report


feature_validation_service = FeatureValidationService()
