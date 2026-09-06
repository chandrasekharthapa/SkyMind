"""Drift Detection Module (Milestone 6).

Measures Feature Drift, Prediction Drift, and Market Drift across historical and current windows.
Generates drift_report.json in `backend/reports/` — see `backend.utils.report_paths`
for why it is no longer written to the repository root.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pandas as pd

from backend.database.database import database as db
from backend.services.booking_curve_definition import ordering_timestamps
from backend.utils.report_paths import report_path, write_report

logger = logging.getLogger(__name__)

REPORT_PATH = report_path("drift_report.json")


class DriftDetectionService:
    def __init__(self):
        pass

    def run_drift_analysis(self, destination: Optional[str] = None) -> Dict[str, Any]:
        """Perform drift analysis across feature, prediction, and market distributions.

        `destination` overrides where the report is written; it defaults to
        `REPORT_PATH`.
        """
        df_raw = db.get_training_dataset()

        if df_raw is None or df_raw.empty or len(df_raw) < 20:
            report = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "feature_drift_score": 0.0,
                "prediction_drift_score": 0.0,
                "market_drift_score": 0.0,
                "overall_drift_status": "STABLE",
                "reason": "Insufficient observations for drift baseline"
            }
            self._save_report(report, destination)
            return report

        # A drift figure is a comparison of an earlier window against a later one,
        # so the ordering is the measurement. This used to be:
        #
        #     ts_col = "search_timestamp" if "search_timestamp" in df_raw.columns \
        #         else ("recorded_at" if ...)
        #     df_raw["_dt"] = pd.to_datetime(df_raw[ts_col])
        #
        # — a fourth hand-rolled copy of the ordering rule, choosing the column by
        # presence and reading only that one. `search_timestamp` was added by
        # migration 001 with no backfill, so on the existing corpus every value is
        # NULL: `_dt` came out all-NaT, NaT sorts last under a stable sort, and the
        # "chronological" sort was therefore a no-op. The 70/30 split below then
        # divided the rows in whatever order Supabase returned them, and every
        # drift score was a comparison of two arbitrary halves reported as
        # baseline-versus-current. `ordering_timestamps` coalesces per row, so a
        # legacy row orders by `recorded_at` instead of vanishing.
        df_raw["_dt"] = ordering_timestamps(df_raw)
        orderable = int(df_raw["_dt"].notna().sum())
        if orderable < 20:
            # Refused rather than split anyway: two arbitrary halves labelled
            # baseline and current produce a number that looks like drift and is
            # not, which is worse than reporting that drift cannot be measured.
            report = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "feature_drift_score": None,
                "prediction_drift_score": None,
                "market_drift_score": None,
                "overall_drift_status": "UNMEASURABLE",
                "reason": (
                    f"only {orderable} of {len(df_raw)} observations carry a usable "
                    f"observation time, so an earlier window cannot be separated "
                    f"from a later one and any drift score would be a comparison "
                    f"of two arbitrary halves"
                ),
            }
            self._save_report(report, destination)
            return report

        df_raw = (
            df_raw[df_raw["_dt"].notna()]
            .sort_values("_dt")
            .reset_index(drop=True)
        )

        split_idx = int(len(df_raw) * 0.70)
        df_baseline = df_raw.iloc[:split_idx]
        df_current = df_raw.iloc[split_idx:]

        # 1. Feature Drift (Price shift)
        p_base_mean = float(df_baseline["price"].mean())
        p_curr_mean = float(df_current["price"].mean())
        price_shift_ratio = abs(p_curr_mean - p_base_mean) / max(1.0, p_base_mean)
        feature_drift_score = float(min(1.0, price_shift_ratio))

        # 2. Prediction Drift (Fare variance change)
        p_base_std = float(df_baseline["price"].std())
        p_curr_std = float(df_current["price"].std())
        var_shift = abs(p_curr_std - p_base_std) / max(1.0, p_base_std)
        prediction_drift_score = float(min(1.0, var_shift))

        # 3. Market Drift (Airline mix / route frequency shifts)
        market_drift_score = float(min(1.0, (feature_drift_score + prediction_drift_score) / 2.0))

        drift_detected = feature_drift_score > 0.40 or prediction_drift_score > 0.40
        status = "DRIFT_DETECTED" if drift_detected else "STABLE"

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "baseline_sample_count": len(df_baseline),
            "current_sample_count": len(df_current),
            "feature_drift_score": round(feature_drift_score, 4),
            "prediction_drift_score": round(prediction_drift_score, 4),
            "market_drift_score": round(market_drift_score, 4),
            "overall_drift_status": status,
            "drift_detected": drift_detected
        }

        self._save_report(report, destination)
        return report

    def _save_report(self, report: Dict[str, Any], destination: Optional[str] = None) -> None:
        write_report(report, destination or REPORT_PATH)


drift_detection_service = DriftDetectionService()
