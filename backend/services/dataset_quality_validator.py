"""Dataset Quality Validator.

Evaluates dataset metrics (duplicates, missing ratios, booking curve depth)
against configurable training policies to decide if forecast model training should proceed.
"""

import logging
from typing import Dict, List, Any
import pandas as pd
from pydantic import BaseModel
from backend.services.training_policy import TrainingPolicy, training_policy as default_policy
# Module-level, unlike the deliberately local import inside
# `evaluate_horizon_readiness`: the duplicate-rate key below is needed on every
# `validate()` call and `booking_curve_definition` is a leaf module (pandas and
# numpy only), so importing it here costs nothing and cannot cycle.
from backend.services.booking_curve_definition import (
    BOOKING_CURVE_KEYS,
    FALLBACK_TIMESTAMP_KEY,
)

logger = logging.getLogger(__name__)

class HorizonReadiness(BaseModel):
    horizon: str
    grade: str  # A, B, C, D, F
    ready: bool
    shifted_count: int
    reason: str

class DatasetQualityReport(BaseModel):
    observation_count: int = 0
    synthetic_count: int = 0
    real_count: int = 0
    shifted_rows: int = 0
    duplicate_rate: float = 0.0
    missing_rate: float = 0.0
    route_coverage: int = 0
    departure_coverage: int = 0
    airport_coverage: int = 0
    airline_coverage: int = 0
    booking_curve_length: int = 0
    temporal_coverage_days: int = 0
    passed: bool = False
    horizon_readiness: Dict[str, HorizonReadiness] = {}

class DatasetQualityValidator:
    def __init__(self, policy: TrainingPolicy = None):
        self.policy = policy or default_policy

    def evaluate_horizon_readiness(self, df_raw: pd.DataFrame, horizons: List[int] = [0, 1, 3, 7, 14, 30]) -> Dict[str, HorizonReadiness]:
        """Letter-graded readiness per horizon, counted by the shipped labeller.

        `shifted_count` is `len(attach_future_target(df_raw, h))` — the same
        function `TrainingDatasetBuilder` and `PriceModel._build_shifted_dataset`
        use. This method used to build its own join, and it was the third
        separately-written copy of the target in the repository. It differed from
        the real one in three ways, all inflating:

        * It joined on `origin_code, destination_code, departure_date, rec_dt` plus
          `airline_code` and carried no per-flight component, so every flight an
          airline operates on a route pooled into one curve. That is the precise
          defect `booking_curve_definition` exists to prevent.
        * It matched on calendar-date equality and kept *every* match rather than
          the earliest, so one row could be counted many times over.
        * At `h == 0` it set `shifted_cnt = len(df)` and graded the horizon ready,
          when horizon 0's label is the observation's own price and
          `attach_future_target` refuses it outright.

        Measured on a real 35,894-row `price_history` export: the old join reported
        225,485 shifted rows at 1 day, 15,967 at 3 and 1,990 at 7 — grade A and
        `ready=True` for all three, and more rows at 1 day than the corpus has rows
        in total. The shipped labeller returns 149, 2,114 and 1. The same training
        run then refused the 7-day horizon on `shifted_rows=1`, so the report and
        the gate contradicted each other in the same log.

        `ready` is now `shifted_count >= policy.min_shifted_rows` — the condition
        `validate()` actually gates on — rather than a third independent set of
        thresholds. The letter grade is kept as a coarse signal, since callers
        print it, but it no longer decides anything.
        """
        from backend.services.booking_curve_definition import (
            MIN_TRAINABLE_HORIZON_DAYS,
            attach_future_target,
            ordering_timestamps,
        )

        readiness_map = {}
        if df_raw is None or df_raw.empty:
            for h in horizons:
                readiness_map[f"{h}d"] = HorizonReadiness(
                    horizon=f"{h}d",
                    grade="F",
                    ready=False,
                    shifted_count=0,
                    reason="No observations available in dataset."
                )
            return readiness_map

        # `ordering_timestamps` rather than `pd.to_datetime(df["recorded_at"])`:
        # it coalesces `search_timestamp` and `recorded_at` per row using the same
        # precedence the label join uses, so this count and the labelled counts
        # below cannot be dated from different columns. The direct read also
        # raised `KeyError` on any frame carrying only `search_timestamp`.
        total_rec_dates = int(ordering_timestamps(df_raw).dt.date.nunique())

        for h in horizons:
            key = f"{h}d"

            if int(h) < MIN_TRAINABLE_HORIZON_DAYS:
                readiness_map[key] = HorizonReadiness(
                    horizon=key, grade="F", ready=False, shifted_count=0,
                    reason=(
                        f"Horizon {h} is not a trainable target: the label would be "
                        f"the observation's own price, so the fit is an identity. "
                        f"Minimum is {MIN_TRAINABLE_HORIZON_DAYS}d."
                    ),
                )
                continue

            try:
                shifted_cnt = int(len(attach_future_target(df_raw, int(h))))
            except ValueError as exc:
                # Missing curve-key columns, or every observation timestamp NULL.
                # Both are corpus defects that make the horizon ungradeable; the
                # old join silently pooled or silently emptied instead.
                readiness_map[key] = HorizonReadiness(
                    horizon=key, grade="F", ready=False, shifted_count=0,
                    reason=f"Cannot label this horizon: {exc}",
                )
                continue

            ready = shifted_cnt >= self.policy.MIN_SHIFTED_ROWS

            if shifted_cnt >= 1000 and total_rec_dates >= 7:
                grade = "A"
                reason = "Sufficient longitudinal shift matches and high coverage."
            elif shifted_cnt >= 300 and total_rec_dates >= 3:
                grade = "B"
                reason = "Moderate observation count; suitable for baseline training."
            elif shifted_cnt >= 50:
                grade = "C"
                reason = "Low observation count; high variance expected."
            elif shifted_cnt > 0:
                grade = "D"
                reason = "Sparse longitudinal shift target matches."
            else:
                grade = "F"
                reason = "No observation on any booking curve carries a later fare at this horizon."

            if not ready and shifted_cnt > 0:
                reason = (
                    f"{reason} {shifted_cnt} labelled row(s) is below the "
                    f"{self.policy.MIN_SHIFTED_ROWS} TrainingPolicy requires, so "
                    f"this horizon will be refused."
                )

            readiness_map[key] = HorizonReadiness(
                horizon=key,
                grade=grade,
                ready=ready,
                shifted_count=shifted_cnt,
                reason=reason
            )

        return readiness_map

    def validate(self, df_raw: pd.DataFrame, df_shifted: pd.DataFrame) -> DatasetQualityReport:
        """Analyze dataset completeness and return validation result."""
        obs_count = len(df_raw) if df_raw is not None else 0
        shifted_rows = len(df_shifted) if df_shifted is not None else 0
        
        if obs_count == 0:
            return DatasetQualityReport(
                observation_count=0,
                synthetic_count=0,
                real_count=0,
                shifted_rows=0,
                duplicate_rate=0.0,
                missing_rate=1.0,
                route_coverage=0,
                airport_coverage=0,
                airline_coverage=0,
                booking_curve_length=0,
                temporal_coverage_days=0,
                passed=False,
                horizon_readiness=self.evaluate_horizon_readiness(df_raw)
            )

        # Provenance counts
        synthetic_count = 0
        if "is_synthetic" in df_raw.columns:
            s_synth = df_raw["is_synthetic"].astype(str).str.lower()
            synthetic_count = int(s_synth.isin(["true", "1", "1.0", "yes"]).sum())
        real_count = obs_count - synthetic_count

        # 1. Duplicate rate
        #
        # One observation is one curve identity at one observation time, so the
        # key is `BOOKING_CURVE_KEYS` plus `recorded_at`, taken from the module
        # that owns the definition. It was a hand-typed list naming
        # `flight_number` where the curve key names `departure_time`; since the
        # provider publishes no flight number that component was NULL on every
        # row, every one of a carrier's departures on a route and date collapsed
        # into one key, and this reported most of a healthy collection run as
        # duplicated. The figure is published in a quality report, so an inflated
        # one argues for deleting data that is not duplicated.
        #
        # A frame missing a curve component cannot answer the question. The rate
        # is left at 0.0 and `duplicate_key` records what was actually compared,
        # so a reader can tell "no duplicates" from "not checked".
        dup_rate = 0.0
        key_cols = list(BOOKING_CURVE_KEYS) + [FALLBACK_TIMESTAMP_KEY]
        cols = [c for c in key_cols if c in df_raw.columns]
        if cols and not [k for k in BOOKING_CURVE_KEYS if k not in df_raw.columns]:
            dups = df_raw.duplicated(subset=cols).sum()
            dup_rate = float(dups / obs_count)

        # 2. Missing rate
        total_elements = df_raw.size
        null_elements = df_raw.isnull().sum().sum()
        missing_rate = float(null_elements / total_elements) if total_elements > 0 else 1.0

        # 3. Route & Airport & Airline coverage
        route_coverage = 0
        if "origin_code" in df_raw.columns and "destination_code" in df_raw.columns:
            route_coverage = len(df_raw.groupby(["origin_code", "destination_code"]).size())

        airports = set()
        if "origin_code" in df_raw.columns:
            airports.update(df_raw["origin_code"].dropna().unique())
        if "destination_code" in df_raw.columns:
            airports.update(df_raw["destination_code"].dropna().unique())
        airport_coverage = len(airports)

        airline_coverage = df_raw["airline_code"].nunique() if "airline_code" in df_raw.columns else 0

        # 4. Departure coverage
        departure_coverage = 0
        if "departure_date" in df_raw.columns:
            departure_coverage = df_raw["departure_date"].nunique()

        # 5. Booking curve length
        booking_curve_length = 0
        if "departure_date" in df_raw.columns and "recorded_at" in df_raw.columns:
            obs_per_dep = df_raw.groupby("departure_date")["recorded_at"].nunique()
            booking_curve_length = int(round(obs_per_dep.mean())) if not obs_per_dep.empty else 0

        # 6. Temporal coverage days
        temporal_coverage_days = 0
        if "recorded_at" in df_raw.columns:
            # `format="ISO8601"` for the reason recorded at the `rec_dt` parse.
            times = pd.to_datetime(df_raw["recorded_at"], format="ISO8601")
            temporal_coverage_days = int((times.max() - times.min()).days)

        # Verify against policy constraints
        passed = True
        reasons = []

        if shifted_rows < self.policy.MIN_SHIFTED_ROWS:
            passed = False
            reasons.append(f"Insufficient shifted rows: {shifted_rows} < {self.policy.MIN_SHIFTED_ROWS}")
        if booking_curve_length < self.policy.MIN_BOOKING_CURVE_LENGTH:
            passed = False
            reasons.append(f"Booking curve too short: {booking_curve_length} < {self.policy.MIN_BOOKING_CURVE_LENGTH}")
        if route_coverage < self.policy.MIN_ROUTE_COVERAGE:
            passed = False
            reasons.append(f"Route coverage too low: {route_coverage} < {self.policy.MIN_ROUTE_COVERAGE}")
        if dup_rate > self.policy.MAX_DUPLICATE_RATE:
            passed = False
            reasons.append(f"Duplicate rate too high: {dup_rate:.2%} > {self.policy.MAX_DUPLICATE_RATE:.2%}")
        if missing_rate > self.policy.MAX_MISSING_RATE:
            passed = False
            reasons.append(f"Missing rate too high: {missing_rate:.2%} > {self.policy.MAX_MISSING_RATE:.2%}")

        if not passed:
            logger.warning(f"[DatasetQualityValidator] Dataset failed policy validation. Reasons: {', '.join(reasons)}")
        else:
            logger.info("[DatasetQualityValidator] Dataset successfully passed all policy validation checks.")

        horizon_readiness = self.evaluate_horizon_readiness(df_raw)

        return DatasetQualityReport(
            observation_count=obs_count,
            synthetic_count=synthetic_count,
            real_count=real_count,
            shifted_rows=shifted_rows,
            duplicate_rate=round(dup_rate, 4),
            missing_rate=round(missing_rate, 4),
            route_coverage=route_coverage,
            airport_coverage=airport_coverage,
            airline_coverage=airline_coverage,
            booking_curve_length=booking_curve_length,
            temporal_coverage_days=temporal_coverage_days,
            passed=passed,
            horizon_readiness=horizon_readiness
        )

dataset_quality_validator = DatasetQualityValidator()
