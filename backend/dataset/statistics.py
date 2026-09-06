"""Statistics & Data Distribution Engine for SkyMind Dataset Pipeline.

Computes comprehensive dataset metrics, coverage statistics, booking window distributions,
missing value matrices, and time-series snapshot densities.
"""

from typing import Dict, Any
import pandas as pd
import numpy as np


class DatasetStatisticsEngine:
    """Computes summary statistics and coverage metrics for dataset v2.0."""

    def compute(self, df_raw: pd.DataFrame, df_cleaned: pd.DataFrame, plugin_results: list = None) -> Dict[str, Any]:
        """Computes comprehensive health report dictionary."""
        total_rows_raw = len(df_raw) if df_raw is not None else 0
        total_rows_clean = len(df_cleaned) if df_cleaned is not None else 0

        # Snapshot density per itinerary_id
        if not df_cleaned.empty and "itinerary_id" in df_cleaned.columns:
            obs_per_itin = df_cleaned.groupby("itinerary_id")["snapshot_sequence"].max() if "snapshot_sequence" in df_cleaned.columns else df_cleaned.groupby("itinerary_id").size()
            unique_itineraries = len(obs_per_itin)
            avg_snapshots = round(float(obs_per_itin.mean()), 2)
            med_snapshots = int(obs_per_itin.median())
            single_obs_pct = round(float((obs_per_itin == 1).sum() / max(unique_itineraries, 1)) * 100.0, 2)
        else:
            unique_itineraries = 0
            avg_snapshots = 0.0
            med_snapshots = 0
            single_obs_pct = 0.0

        # Rejected count totals from plugins
        rejected_rows = total_rows_raw - total_rows_clean
        duplicate_rows = 0
        days_mismatches = 0
        for res in (plugin_results or []):
            if getattr(res, "plugin_name", "") == "duplicate_validation":
                duplicate_rows = getattr(res, "rejected_rows_count", 0)
            elif getattr(res, "plugin_name", "") == "chronology_validation":
                days_mismatches = getattr(res, "rejected_rows_count", 0)

        # Booking window distribution
        booking_window_counts = {}
        if not df_cleaned.empty and "booking_window" in df_cleaned.columns:
            booking_window_counts = df_cleaned["booking_window"].value_counts().to_dict()

        # Missing values matrix
        missing_matrix = {}
        if not df_cleaned.empty:
            null_counts = df_cleaned.isnull().sum()
            missing_matrix = {col: int(cnt) for col, cnt in null_counts.items() if cnt > 0}

        validation_status = "PASS" if days_mismatches == 0 and total_rows_clean > 0 else "FAIL"

        return {
            "summary": {
                "total_rows_raw": total_rows_raw,
                "total_rows_clean": total_rows_clean,
                "unique_itineraries": unique_itineraries,
                "average_snapshots_per_itinerary": avg_snapshots,
                "median_snapshots_per_itinerary": med_snapshots,
                "single_observation_itineraries_pct": single_obs_pct,
                "invalid_rows_rejected": rejected_rows,
                "duplicate_rows_removed": duplicate_rows,
                "days_until_dep_mismatches": days_mismatches,
                "empty_prohibited_columns_count": 0,
                "validation_status": validation_status
            },
            "distributions": {
                "booking_window_counts": booking_window_counts
            },
            "data_integrity": {
                "missing_values_matrix": missing_matrix
            }
        }


dataset_statistics_engine = DatasetStatisticsEngine()
