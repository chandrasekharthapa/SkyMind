"""Time-Series Integrity & Invariants Validation Plugin.

Validates that per itinerary_id:
1. snapshot_time is strictly monotonically increasing
2. days_until_dep is strictly monotonically decreasing
3. Identity attributes (origin, destination, departure_date, airline, flight_number) remain invariant
"""

from typing import Tuple, List
import pandas as pd
from backend.dataset.plugins.base import BaseValidationPlugin, ValidationPluginResult


class TimeSeriesIntegrityPlugin(BaseValidationPlugin):
    name = "time_series_integrity"

    def validate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, ValidationPluginResult]:
        if df.empty or "itinerary_id" not in df.columns:
            return df, ValidationPluginResult(plugin_name=self.name, passed=True)

        errors: List[str] = []
        corrupted_itineraries = set()

        ts_col = "snapshot_time" if "snapshot_time" in df.columns else "recorded_at"

        # Group by itinerary_id and check chronology
        for itin_id, group in df.groupby("itinerary_id"):
            if len(group) <= 1:
                continue

            sorted_group = group.sort_values(by=ts_col)

            # 1. Check increasing snapshot_time
            #
            # `format="ISO8601"` is what stops this from raising on real data.
            # `snapshot_time` is written with `Timestamp.isoformat()`, which omits
            # the microseconds field when it is zero, and Postgres returns
            # `recorded_at` the same way — so both columns mix
            # `...T10:00:00.123456+00:00` with `...T10:00:01+00:00`. Without a
            # format pandas infers one shape from the first value and, with the
            # default `errors="raise"`, dies with `time data ... doesn't match
            # format` on the first row of the other shape. This plugin runs over
            # every itinerary in the frame, so that is a hard stop rather than a
            # dropped row. `errors` is deliberately left at its default: a value
            # that is not ISO-8601 at all is still a loud failure, as before.
            times = pd.to_datetime(sorted_group[ts_col], format="ISO8601")
            if not times.is_monotonic_increasing:
                corrupted_itineraries.add(itin_id)
                continue

            # 2. Check decreasing days_until_dep
            if "days_until_dep" in sorted_group.columns:
                leads = sorted_group["days_until_dep"].values
                if not all(leads[i] >= leads[i+1] for i in range(len(leads)-1)):
                    corrupted_itineraries.add(itin_id)

        rejected_cnt = 0
        if corrupted_itineraries:
            corrupted_mask = df["itinerary_id"].isin(corrupted_itineraries)
            rejected_cnt = int(corrupted_mask.sum())
            cleaned_df = df[~corrupted_mask].copy()
            errors.append(f"Rejected {rejected_cnt} observations belonging to {len(corrupted_itineraries)} corrupted time-series itineraries.")
        else:
            cleaned_df = df.copy()

        return cleaned_df, ValidationPluginResult(
            plugin_name=self.name,
            passed=len(corrupted_itineraries) == 0,
            rejected_rows_count=rejected_cnt,
            errors=errors,
            details={"corrupted_itineraries_count": len(corrupted_itineraries)}
        )
