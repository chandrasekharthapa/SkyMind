"""Duplicate Observation Detection & Rejection Plugin."""

from typing import Tuple, List
import pandas as pd
from backend.dataset.plugins.base import BaseValidationPlugin, ValidationPluginResult
from backend.services.booking_curve_definition import (
    BOOKING_CURVE_KEYS,
    FALLBACK_TIMESTAMP_KEY,
)


class DuplicateValidationPlugin(BaseValidationPlugin):
    name = "duplicate_validation"

    def validate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, ValidationPluginResult]:
        if df.empty:
            return df, ValidationPluginResult(plugin_name=self.name, passed=True)

        # One observation is one curve identity at one observation time. The key
        # is `BOOKING_CURVE_KEYS` rather than a hand-typed list, because this
        # plugin *deletes* the rows it decides are duplicates and a key that is
        # too coarse deletes real data silently.
        #
        # It was hand-typed, and it named `flight_number` where the curve key now
        # names `departure_time`. The provider publishes no flight number, so that
        # component was NULL on every row and could not separate anything: two of
        # a carrier's departures on the same route, date and observation run
        # collided whenever they were priced the same, and the later one was
        # dropped. That is not hypothetical — a live 65-flight DEL-BOM fetch had
        # 5 airlines over 15 distinct prices, and its 7 one-stop flights were all
        # priced identically at Rs 5,985.
        #
        # `price` stays in the key. It is not part of the curve identity, but two
        # rows agreeing on identity *and* observation time *and* fare are the same
        # observation submitted twice; if they disagree on fare, keeping both is
        # correct and the disagreement is the finding.
        dedup_keys = list(BOOKING_CURVE_KEYS) + [FALLBACK_TIMESTAMP_KEY, "price"]
        actual_keys = [k for k in dedup_keys if k in df.columns]

        # A frame missing every curve component cannot be de-duplicated on
        # identity, and de-duplicating it on whatever is left — in practice
        # `(recorded_at, price)` — would collapse unrelated flights that happen to
        # share a fare. Pass it through untouched and say so.
        missing_identity = [k for k in BOOKING_CURVE_KEYS if k not in df.columns]
        if missing_identity or not actual_keys:
            return df, ValidationPluginResult(
                plugin_name=self.name,
                passed=True,
                errors=[
                    "Not de-duplicated: the frame is missing "
                    f"{', '.join(missing_identity) or 'every key column'}, so no "
                    "row can be identified and any narrower key would delete "
                    "distinct flights."
                ] if missing_identity else [],
                details={"duplicate_rows_removed": 0,
                         "missing_identity_columns": missing_identity},
            )

        duplicated_mask = df.duplicated(subset=actual_keys, keep="first")
        duplicate_cnt = int(duplicated_mask.sum())
        cleaned_df = df[~duplicated_mask].copy()

        errors = []
        if duplicate_cnt > 0:
            errors.append(f"Removed {duplicate_cnt} duplicate observation rows.")

        return cleaned_df, ValidationPluginResult(
            plugin_name=self.name,
            passed=duplicate_cnt == 0,
            rejected_rows_count=duplicate_cnt,
            errors=errors,
            details={"duplicate_rows_removed": duplicate_cnt,
                     "dedup_key": actual_keys}
        )
