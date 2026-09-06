"""Chronology & Calendar Date Subtraction Validation Plugin.

Validates that:
1. days_until_dep == (departure_date.date() - recorded_at.date()).days
2. departure_date >= recorded_at.date() (booking before departure)
"""

from typing import Tuple, List
import pandas as pd
from backend.dataset.plugins.base import BaseValidationPlugin, ValidationPluginResult
from backend.dataset.dates import parse_to_date
from backend.services.booking_curve_definition import ordering_timestamps


class ChronologyValidationPlugin(BaseValidationPlugin):
    name = "chronology_validation"

    def validate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, ValidationPluginResult]:
        errors: List[str] = []
        if df.empty:
            return df, ValidationPluginResult(plugin_name=self.name, passed=True)

        dep_dates = df["departure_date"].apply(parse_to_date)
        # `ts_col = "recorded_at" if "recorded_at" in df.columns else
        # "search_timestamp"` was the third copy of the ordering rule and the
        # second one with the preference inverted, so this plugin measured
        # `days_until_dep` against the insert date while the writer computed it
        # against the search date. It also indexed `search_timestamp`
        # unconditionally in the `else` branch, raising `KeyError` on a frame
        # carrying neither column instead of reporting an unvalidatable frame.
        observed = ordering_timestamps(df)
        undated = int(observed.isna().sum())
        if undated == len(df):
            return df.iloc[0:0].copy(), ValidationPluginResult(
                plugin_name=self.name,
                passed=False,
                rejected_rows_count=len(df),
                errors=[
                    f"No row carries a usable observation time (neither "
                    f"search_timestamp nor recorded_at), so days_until_dep cannot "
                    f"be checked against calendar date subtraction for any of the "
                    f"{len(df)} rows."
                ],
                details={"days_until_dep_mismatches": len(df)},
            )

        rec_dates = observed.dt.date
        # A row with no observation time cannot satisfy the check, so it is
        # rejected — `expected_days` is NaT-derived and every comparison against
        # it is False, which would otherwise reject it with a misleading reason.
        expected_days = pd.Series(
            [(d - r).days if pd.notna(r) else pd.NA
             for d, r in zip(dep_dates, rec_dates)],
            index=df.index, dtype="Int64",
        )

        # Chronology condition 1: booking must not be after departure
        valid_dep = (expected_days >= 0).fillna(False)

        # Chronology condition 2: if days_until_dep present, it must match exact integer
        if "days_until_dep" in df.columns:
            claimed = pd.to_numeric(df["days_until_dep"], errors="coerce").astype("Int64")
            valid_mismatch = (claimed == expected_days).fillna(False)
            valid_mask = valid_dep & valid_mismatch
        else:
            valid_mask = valid_dep
            df["days_until_dep"] = expected_days

        rejected_cnt = int((~valid_mask).sum())
        cleaned_df = df[valid_mask].copy()

        if rejected_cnt > 0:
            detail = (f" ({undated} of them carry no observation time)"
                      if undated else "")
            errors.append(
                f"Rejected {rejected_cnt} rows failing calendar date subtraction "
                f"or booking after departure{detail}."
            )

        return cleaned_df, ValidationPluginResult(
            plugin_name=self.name,
            passed=rejected_cnt == 0,
            rejected_rows_count=rejected_cnt,
            errors=errors,
            details={"days_until_dep_mismatches": rejected_cnt}
        )
