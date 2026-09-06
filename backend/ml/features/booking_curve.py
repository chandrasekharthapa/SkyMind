"""Booking-curve features.

Every quantity here is computed by a function in
`backend.services.booking_curve_definition`, called by *both* the training path
and the inference path. That is the point of the module: before the 2026-08 fix
pass the two branches of `transform` were independent implementations, and they
disagreed in five measurable ways under identical feature names —

  * lags were `groupby(...).shift(n)` in training and `curve_points[-(n+1)]` at
    inference, both positional, both named as day-based changes;
  * the grouping omitted `flight_number`, so `shift(1)` crossed between two
    different flights on the same route, date and airline;
  * training sorted on `recorded_at` while the target join sorted on
    `search_timestamp`, so the two disagreed about which row came first;
  * `rolling_price_std` was pandas' sample std (ddof=1) in training and
    `np.std` (ddof=0) at inference;
  * `booking_curve_progress` divided by `(a+b).clip(lower=1)` in training and by
    `a+b` at inference.

Nothing here fills a missing value with 0.0. Three `.fillna(0.0)` calls used to,
which reported "no change", "flat curve" and "no variation" for observations that
had nothing to compare against. XGBoost consumes NaN natively.
"""

from typing import List, Dict, Any
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from backend.ml.feature_generator import FeatureGenerator
from backend.ml.feature_context import FeatureContext
from backend.services.booking_curve_definition import (
    ROLLING_WINDOW_OBSERVATIONS,
    booking_curve_progress,
    booking_horizon_days,
    booking_horizon_from_dates,
    curve_group_columns,
    curve_identity_from_record,
    curve_identity_is_complete,
    curve_identity_mask,
    curve_slope_acceleration,
    get_booking_curve_group_key,
    ordering_timestamps,
    price_at_lag,
    rolling_price_statistics,
)

# The three day-based change features and the lag each one means. The names are
# the contract: `price_change_3d` is the change against an observation three days
# earlier, resolved as-of, or null.
LAG_DAYS: Dict[str, int] = {
    "price_change_1d": 1,
    "price_change_3d": 3,
    "price_change_7d": 7,
}


class BookingCurveGenerator(FeatureGenerator):
    @property
    def name(self) -> str:
        return "BookingCurveGenerator"

    @property
    def feature_names(self) -> List[str]:
        return [
            # Legacy booking curve
            "seats_available", "price_change_1d", "price_change_3d",
            # V1 booking curve
            "days_since_first_observation", "observation_count", "booking_curve_progress",
            "rolling_mean_price", "rolling_median_price", "rolling_min_price",
            "rolling_max_price", "rolling_price_std", "price_change_7d",
            "price_slope", "price_acceleration",
        ]

    @property
    def category(self) -> str:
        return "booking_curve"

    @property
    def version(self) -> str:
        # 2.0.0: time-based lags on the full booking-curve key, shared
        # definitions with the inference path, no zero-filling.
        return "2.0.0"

    def transform(self, context: FeatureContext) -> Dict[str, Any]:
        if isinstance(context.historical_data, pd.DataFrame):
            return self._transform_training(context.historical_data)
        return self._transform_inference(context)

    # ── Training: a frame of observations, one row out per row in ──────
    def _transform_training(self, raw: pd.DataFrame) -> Dict[str, pd.Series]:
        if raw.empty:
            return {n: pd.Series(dtype="float64") for n in self.feature_names}

        if raw.index.has_duplicates:
            # The returned Series are aligned back onto the caller's frame by
            # index label (`feature_engineering_pipeline.build_training_dataset`
            # assigns them into a frame built with `index=dataframe.index`). A
            # duplicated label makes that alignment ambiguous, so refuse rather
            # than emit a silently mispaired feature column.
            raise ValueError(
                "BookingCurveGenerator requires a unique index: features are "
                "aligned back to the caller's frame by index label."
            )

        group_cols = curve_group_columns(raw)
        if not group_cols:
            raise ValueError(
                "BookingCurveGenerator found none of the booking-curve key "
                f"columns on a frame with columns {sorted(raw.columns)[:12]}. "
                "Without a curve identity every observation would be treated as "
                "belonging to one shared price history."
            )

        df = raw.copy()
        df["_ts"] = ordering_timestamps(df)
        price = pd.to_numeric(df["price"], errors="coerce") if "price" in df.columns \
            else pd.Series(np.nan, index=df.index)
        df["_price"] = price

        # An observation whose curve key is incomplete has no curve, so it takes
        # no curve features. The mask has to gate the *grouping*, not just the
        # output: `groupby(..., dropna=False)` gives every null-keyed row one
        # shared group, so without it a route/date/airline with three unnumbered
        # flights becomes a single three-point "price history" and `price_at_lag`
        # crosses between them — the defect `flight_number` was added to the key
        # to stop. Ingest no longer substitutes a flight number when the provider
        # omits one, which is why such rows now reach here at all.
        identified = curve_identity_mask(df)
        curve = df[identified]
        if curve.empty:
            unknown = {n: pd.Series(np.nan, index=raw.index, dtype="float64")
                       for n in self.feature_names}
            unknown["seats_available"] = (
                pd.to_numeric(raw["seats_available"], errors="coerce")
                if "seats_available" in raw.columns
                else pd.Series(np.nan, index=raw.index, dtype="float64")
            )
            return unknown

        # 1. Day-based changes, as-of, on the full curve key.
        changes: Dict[str, pd.Series] = {}
        for feat, back in LAG_DAYS.items():
            prior = price_at_lag(curve, back, price_col="_price", group_cols=group_cols)
            changes[feat] = (curve["_price"] - prior).reindex(df.index)

        # 2. Per-curve sequential quantities. One pass per curve, in observation
        #    order, calling the same helpers the inference path calls.
        cols = ["days_since_first_observation", "observation_count",
                "booking_curve_progress", "rolling_mean_price",
                "rolling_median_price", "rolling_min_price", "rolling_max_price",
                "rolling_price_std", "price_slope", "price_acceleration"]
        acc: Dict[str, Dict[Any, float]] = {c: {} for c in cols}

        # The horizon is derived here, not read from `days_until_dep`. That column
        # is an ingest-time denormalisation of `departure_date - recorded_at`, and
        # the serving path has no such column to read — it derived the value from
        # the request, so the same feature was computed two different ways on the
        # two paths. `booking_horizon_days` is what both call now.
        horizon = booking_horizon_days(curve, observed=curve["_ts"])
        for _, grp in curve.groupby(group_cols, sort=False, dropna=False):
            grp = grp.sort_values("_ts", kind="mergesort")
            times = grp["_ts"].tolist()
            prices = grp["_price"].tolist()
            first_ts = next((t for t in times if pd.notna(t)), pd.NaT)
            for i, idx in enumerate(grp.index):
                stats = rolling_price_statistics(prices[: i + 1],
                                                 window=ROLLING_WINDOW_OBSERVATIONS)
                shape = curve_slope_acceleration(times[: i + 1], prices[: i + 1])
                if pd.isna(times[i]) or pd.isna(first_ts):
                    days_since = float("nan")
                else:
                    days_since = (times[i] - first_ts).total_seconds() / 86400.0
                until = float(horizon.loc[idx])

                acc["days_since_first_observation"][idx] = days_since
                acc["observation_count"][idx] = float(i + 1)
                acc["booking_curve_progress"][idx] = booking_curve_progress(days_since, until)
                acc["rolling_mean_price"][idx] = stats["mean"]
                acc["rolling_median_price"][idx] = stats["median"]
                acc["rolling_min_price"][idx] = stats["min"]
                acc["rolling_max_price"][idx] = stats["max"]
                acc["rolling_price_std"][idx] = stats["std"]
                acc["price_slope"][idx] = shape["slope"]
                acc["price_acceleration"][idx] = shape["acceleration"]

        features: Dict[str, pd.Series] = {
            c: pd.Series(acc[c], dtype="float64").reindex(df.index) for c in cols
        }
        features.update(changes)
        features["seats_available"] = (
            pd.to_numeric(df["seats_available"], errors="coerce")
            if "seats_available" in df.columns
            else pd.Series(np.nan, index=df.index, dtype="float64")
        )
        return features

    # ── Inference: one request, plus whatever history was retrieved ────
    def _transform_inference(self, context: FeatureContext) -> Dict[str, Any]:
        ctx = context.prediction_context
        # `curve_identity_from_record`, not a hand-typed dict. This was a literal
        # naming `flight_number`, and everything below reads it through
        # `BOOKING_CURVE_KEYS` — so after the per-flight component became
        # `departure_time` on 2026-09-03 the dict no longer carried the component
        # the key asks for. `curve_identity_is_complete` then returned False for
        # every request and this generator's 14 features came back NaN even when
        # the caller had resolved a departure time, which `prediction_service` does.
        query = curve_identity_from_record(ctx)
        target_key = get_booking_curve_group_key(query)
        current_price = ctx.get("current_price")
        seats = ctx.get("seats_available")

        # A request that does not name a flight is not asking about a curve, and
        # there is no honest curve feature to return for it. Before this check the
        # five-part key was built with `flight_number` rendered as `"NONE"`, so no
        # retrieved observation could match it and the whole block was computed
        # from the quoted fare alone: `observation_count` 1.0,
        # `days_since_first_observation` 0.0, `booking_curve_progress` 0.0 and each
        # `rolling_*` equal to that one fare. The model was fitted on the same
        # names computed over real curves — measured on a five-day curve, 11 of
        # the 14 features here differed between the two paths, and once the flight
        # is named all 14 agree exactly.
        if not curve_identity_is_complete(query):
            features = {n: np.nan for n in self.feature_names}
            features["seats_available"] = float(seats) if seats is not None else np.nan
            return features

        # Chronological sequence of this curve's observations. Matched on the
        # same five-part key the training grouping uses, so a request cannot be
        # served from a different flight's history.
        rows: List[Dict[str, Any]] = []
        for row in (context.historical_data or []):
            if not isinstance(row, dict):
                continue
            # Same shared reader as `query` above, so a retrieved row and the
            # request are reduced to a curve identity by one definition. Hand-typed
            # here too, and the comparison below is `get_booking_curve_group_key`,
            # which iterates `BOOKING_CURVE_KEYS`: the omitted component rendered as
            # `"NONE"` on both sides, so every retrieved observation of the route,
            # date and airline matched — a sibling departure's fares read as this
            # flight's own history.
            candidate = curve_identity_from_record(row)
            if get_booking_curve_group_key(candidate) != target_key:
                continue
            ts = row.get("search_timestamp") or row.get("recorded_at") or row.get("recorded_date")
            if ts is None or row.get("price") is None:
                continue
            rows.append({**candidate, "search_timestamp": ts, "price": row.get("price")})

        # The fare being quoted now is an observation on this curve, and it is
        # known at prediction time, so it belongs at the end of the sequence.
        # Its timestamp is the request time.
        now = context.current_timestamp or datetime.now(timezone.utc)
        if current_price is not None and not (isinstance(current_price, float)
                                              and np.isnan(current_price)):
            rows.append({**query, "search_timestamp": now, "price": float(current_price)})

        features: Dict[str, Any] = {
            "seats_available": float(seats) if seats is not None else np.nan,
        }
        if not rows:
            for name in self.feature_names:
                features.setdefault(name, np.nan)
            features["observation_count"] = 0.0
            return features

        df = pd.DataFrame(rows)
        df["_ts"] = ordering_timestamps(df)
        df["_price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df.sort_values("_ts", kind="mergesort").reset_index(drop=True)
        group_cols = curve_group_columns(df)

        # Same function, same arguments as training. The last row is the request.
        for feat, back in LAG_DAYS.items():
            prior = price_at_lag(df, back, price_col="_price", group_cols=group_cols)
            features[feat] = float(df["_price"].iloc[-1] - prior.iloc[-1]) \
                if pd.notna(prior.iloc[-1]) and pd.notna(df["_price"].iloc[-1]) else np.nan

        times = df["_ts"].tolist()
        prices = df["_price"].tolist()
        stats = rolling_price_statistics(prices, window=ROLLING_WINDOW_OBSERVATIONS)
        shape = curve_slope_acceleration(times, prices)

        first_ts = next((t for t in times if pd.notna(t)), pd.NaT)
        days_since = float("nan") if (pd.isna(times[-1]) or pd.isna(first_ts)) \
            else (times[-1] - first_ts).total_seconds() / 86400.0

        # The horizon, from the same function the training path calls. This read
        # `ctx["days_until_dep"]` first and fell back to
        # `max(0, (dep - now.date()).days)` — a caller-supplied number in
        # preference to the derived one, and a clamp that turned a departure
        # already past into "departing today" instead of an unknown horizon.
        days_until_f = booking_horizon_from_dates(query["departure_date"], now)

        features["days_since_first_observation"] = days_since
        features["observation_count"] = float(len(df))
        features["booking_curve_progress"] = booking_curve_progress(days_since, days_until_f)
        features["rolling_mean_price"] = stats["mean"]
        features["rolling_median_price"] = stats["median"]
        features["rolling_min_price"] = stats["min"]
        features["rolling_max_price"] = stats["max"]
        features["rolling_price_std"] = stats["std"]
        features["price_slope"] = shape["slope"]
        features["price_acceleration"] = shape["acceleration"]
        return features
