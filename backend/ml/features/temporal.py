"""Calendar features of the departure, and the booking horizon against it.

Four things in this module used to report a fabricated number where the honest
answer is "unknown", and one crashed:

  * **A scalar into `pd.to_datetime`.** `df.get("recorded_at",
    df.get("recorded_date", context.current_timestamp))` returns a *Timestamp*
    when neither column is present, so `pd.to_datetime` produced a scalar and the
    next line raised `AttributeError: 'Timestamp' object has no attribute 'dt'`.
    A frame with no observation timestamp is a legitimate input — it is what the
    leakage check builds when it wants to know whether a feature depends on the
    ordering column — and it took the whole pipeline down.

  * **`days_until_dep` filled with 0 and clipped at 0.** Zero days until
    departure is the single most urgent booking state there is, and `urgency =
    1/(days+1)` turns it into the maximum of that feature too. Both an
    unparseable date and a departure recorded *before* the observation were
    reported as "departs today". `database.py` already decided this the other
    way — "No observation timestamp means the horizon is unknowable. Do not
    substitute the current date" — and this module now agrees with it.

  * **Calendar fields filled with -1.** `day_of_week`, `month`, `week_of_year`
    and their four `departure_*` twins were `.fillna(-1).astype(int)`, so a row
    with no readable departure date arrived at the model as a weekday of -1: a
    number on the same axis as the real ones, one step below Monday.

  * **`is_peak_hour` filled with 0.0 while `hour_of_day` was NaN.** `hours.isin(
    [...])` is False for NaN, so an unreadable departure time reported "not a
    peak-hour flight" rather than "unknown".

  * **Inference substituting today's date for a missing departure date.**
    Training reported -1 for the same row. Two different fabrications under one
    feature name.

`hour_of_day` and `is_peak_hour` are computed from a `departure_time` column that
`price_history` did not have and no writer populated, so both were NaN for 100% of
every training frame while the serving path read the hour straight off the
provider's segment and supplied it. A feature present only at inference is one the
model cannot have learned to use. `departure_time` is now captured at ingest
(`ingestion_controller.format_payload`, `flight_search_service`, `bash.py`) and
added by migration 001; rows written before that stay NULL, and this module leaves
them NaN rather than inferring an hour from the date.
"""

from typing import List, Dict, Any
from datetime import datetime, date

import pandas as pd
import numpy as np

from backend.ml.feature_generator import FeatureGenerator
from backend.ml.feature_context import FeatureContext
from backend.services.booking_curve_definition import (
    booking_horizon_days,
    booking_horizon_from_dates,
    ordering_timestamps,
)

PEAK_HOURS = (7, 8, 9, 10, 17, 18, 19, 20)


class TemporalGenerator(FeatureGenerator):
    @property
    def name(self) -> str:
        return "TemporalGenerator"

    @property
    def feature_names(self) -> List[str]:
        return [
            # Legacy temporal
            "days_until_dep", "urgency", "day_of_week", "month", "week_of_year",
            "hour_of_day", "is_peak_hour",
            # V1 temporal
            "departure_day_of_week", "departure_month", "departure_quarter",
            "departure_week", "is_weekend", "is_holiday", "is_long_weekend",
            "days_until_departure",
        ]

    @property
    def category(self) -> str:
        return "temporal"

    @property
    def version(self) -> str:
        # 2.0.0: no -1 calendar sentinels, no zero-filled booking horizon, no
        # substituted current date, and a frame with no timestamp column no
        # longer raises.
        return "2.0.0"

    def _is_holiday_date(self, d: date) -> bool:
        # Standard deterministic Indian holidays (as a fallback)
        return (d.month == 1 and d.day == 26) or \
               (d.month == 8 and d.day == 15) or \
               (d.month == 10 and d.day == 2) or \
               (d.month == 12 and d.day == 25) or \
               (d.month == 1 and d.day == 1)

    def _is_long_weekend_date(self, d: date) -> bool:
        # If Friday is holiday, adjacent weekend is long weekend. If Monday is holiday, same.
        if d.weekday() == 4:  # Friday
            return self._is_holiday_date(d)
        if d.weekday() == 0:  # Monday
            return self._is_holiday_date(d)
        return False

    def transform(self, context: FeatureContext) -> Dict[str, Any]:
        if isinstance(context.historical_data, pd.DataFrame):
            return self._transform_training(context.historical_data)
        return self._transform_inference(context)

    # ── Training: a frame of observations ──────────────────────────────
    def _observation_times(self, df: pd.DataFrame) -> pd.Series:
        """When each fare was observed, or NaT — never the current time.

        `ordering_timestamps` resolves `search_timestamp` then `recorded_at` and
        returns all-NaT when neither is present, so this cannot hand a scalar to
        `.dt` the way the old `df.get(..., current_timestamp)` chain did.
        """
        times = ordering_timestamps(df)
        if times.isna().all() and "recorded_date" in df.columns:
            times = pd.to_datetime(df["recorded_date"], errors="coerce", utc=True)
        return pd.Series(times.values, index=df.index)

    def _transform_training(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        nan = pd.Series(np.nan, index=df.index, dtype="float64")
        if "departure_date" in df.columns:
            # `format="ISO8601", utc=True` for the reason recorded in
            # `booking_curve_definition.booking_horizon_days`: without the format a
            # column mixing a bare date with a full timestamp loses one shape to
            # NaT, and without `utc=True` the format returns object dtype and the
            # `.dt` access below raises. The tz is stripped four lines down, so a
            # naive input is unchanged.
            dep = pd.to_datetime(df["departure_date"], errors="coerce", utc=True,
                                 format="ISO8601")
        else:
            dep = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
        rec = self._observation_times(df)

        if getattr(dep.dt, "tz", None) is not None:
            dep = dep.dt.tz_localize(None)
        if getattr(rec.dt, "tz", None) is not None:
            rec = rec.dt.tz_localize(None)
        # Date-only, so the horizon is a whole number of days on both paths.
        dep = dep.dt.normalize()
        rec = rec.dt.normalize()

        # No `.fillna(0)`, and no `.clip(lower=0)`: an unreadable date and a
        # departure that precedes the observation are both unknown horizons, not
        # departures today. `booking_horizon_days` is the single definition —
        # `booking_curve_progress` and `average_booking_lead` call it too, so one
        # vector can no longer carry three horizons.
        days_until_dep = booking_horizon_days(df, observed=rec)
        urgency = 1.0 / (days_until_dep + 1.0)

        day_of_week = dep.dt.weekday.astype("float64")
        month = dep.dt.month.astype("float64")
        week_of_year = dep.dt.isocalendar().week.astype("float64")
        quarter = dep.dt.quarter.astype("float64")

        hours = nan.copy()
        if "departure_time" in df.columns:
            hours = pd.to_datetime(df["departure_time"], errors="coerce") \
                .dt.hour.astype("float64")
        # `.isin` is False for NaN, which reported "not a peak-hour flight" for
        # every row whose departure time could not be read.
        is_peak = hours.isin(PEAK_HOURS).astype("float64").where(hours.notna())

        known = dep.notna()
        is_weekend = (day_of_week >= 5).astype("float64").where(known)
        is_holiday = dep.map(
            lambda x: float(self._is_holiday_date(x.date())) if pd.notna(x) else np.nan
        ).astype("float64")
        is_long_weekend = dep.map(
            lambda x: float(self._is_long_weekend_date(x.date())) if pd.notna(x) else np.nan
        ).astype("float64")

        return {
            "days_until_dep": days_until_dep,
            "urgency": urgency,
            "day_of_week": day_of_week,
            "month": month,
            "week_of_year": week_of_year,
            "hour_of_day": hours,
            "is_peak_hour": is_peak,
            "departure_day_of_week": day_of_week,
            "departure_month": month,
            "departure_quarter": quarter,
            "departure_week": week_of_year,
            "is_weekend": is_weekend,
            "is_holiday": is_holiday,
            "is_long_weekend": is_long_weekend,
            "days_until_departure": days_until_dep,
        }

    # ── Inference: one request ─────────────────────────────────────────
    def _transform_inference(self, context: FeatureContext) -> Dict[str, Any]:
        ctx = context.prediction_context
        dep_date_str = ctx.get("departure_date")
        dep_time_str = ctx.get("departure_time")

        hour_of_day: Any = np.nan
        is_peak_hour: Any = np.nan
        # Training reads this column with `pd.to_datetime(...).dt.hour`, which accepts
        # more shapes than the split below. The two agree because every value
        # reaching either path has been through
        # `MarketDataController.normalize_departure_time`, which guarantees a full
        # ISO timestamp or None — at ingest for the stored column, and in
        # `prediction_service` for the live snapshot. A caller that passes a raw
        # provider string gets NaN here for a time training would have parsed.
        if dep_time_str and "T" in str(dep_time_str):
            try:
                hour_of_day = float(str(dep_time_str).split("T")[1].split(":")[0])
                is_peak_hour = 1.0 if hour_of_day in PEAK_HOURS else 0.0
            except (IndexError, ValueError):
                pass

        dep_dt = None
        if dep_date_str:
            try:
                dep_dt = datetime.strptime(str(dep_date_str)[:10], "%Y-%m-%d").date()
            except (TypeError, ValueError):
                dep_dt = None

        if dep_dt is None:
            # Was `context.current_timestamp.date()`: a request with no departure
            # date got today's calendar features, which is a different flight.
            unknown: Dict[str, Any] = {name: np.nan for name in self.feature_names}
            unknown["hour_of_day"] = hour_of_day
            unknown["is_peak_hour"] = is_peak_hour
            return unknown

        # The same definition the training path uses, so the horizon a request
        # is scored on is the horizon the model was fitted on.
        days_until_dep = booking_horizon_from_dates(dep_dt, context.current_timestamp)
        urgency: Any = (1.0 / (days_until_dep + 1.0)
                        if not np.isnan(days_until_dep) else np.nan)

        day_of_week = dep_dt.weekday()
        month = dep_dt.month
        return {
            "days_until_dep": days_until_dep,
            "urgency": urgency,
            "day_of_week": day_of_week,
            "month": month,
            "week_of_year": dep_dt.isocalendar()[1],
            "hour_of_day": hour_of_day,
            "is_peak_hour": is_peak_hour,
            "departure_day_of_week": day_of_week,
            "departure_month": month,
            "departure_quarter": (month - 1) // 3 + 1,
            "departure_week": dep_dt.isocalendar()[1],
            # Kept as a Python bool, which `test_temporal_features.py` asserts
            # identity against. The training branch cannot: a bool Series has no
            # room for "the departure date could not be read".
            "is_weekend": day_of_week >= 5,
            "is_holiday": self._is_holiday_date(dep_dt),
            "is_long_weekend": self._is_long_weekend_date(dep_dt),
            "days_until_departure": days_until_dep,
        }
