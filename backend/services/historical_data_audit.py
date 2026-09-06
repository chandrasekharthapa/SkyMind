"""Historical Data Audit Module (Milestone 4).

Evaluates route coverage, booking curve density, observation count,
missing value percentage, duplicate observations, and feature completeness.

Three things about the report this produced were wrong, and all three made a
worse dataset look like a better one.

The destination was the repository root, and the file there is tracked — see
`backend.utils.report_paths`. It now writes to `backend/reports/`.

The status was `"PASS" if total_obs >= 100 and missing_pct <= 50.0 else
"WARNING"`, which gated on two of the five things the method measures and could
not return FAIL on any non-empty frame. The committed 2026-07-27 report is the
demonstration: `duplicate_observation_percentage: 20.0` with `status: "PASS"`,
because duplicates were computed, written out, and then not consulted. Every
measured figure now has a threshold, and FAIL is reachable.

And `booking_curve_density_avg` was `total_obs / route_count` — observations per
*route*, published under the name of observations per *booking curve*. A route
carries many departures across many departure dates, so on the committed report
that inflated the figure by however many curves the 8 routes contain: it read
125.0 when a curve is `BOOKING_CURVE_KEYS` (origin, destination, airline,
scheduled departure instant, departure date), not `origin-destination`. Density is
now counted over the real key, with observations-per-route kept as its own
separate figure.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.database.database import database as db
from backend.services.booking_curve_definition import (
    BOOKING_CURVE_KEYS,
    FALLBACK_TIMESTAMP_KEY,
    ORDERING_TIMESTAMP_KEY,
    curve_group_columns,
)
from backend.utils.report_paths import report_path, write_report

logger = logging.getLogger(__name__)

REPORT_PATH = report_path("historical_data_report.json")

# What the status gate requires. Each bound is named so a report that fails can
# say which one it failed, and so raising a bar is an edit here rather than a
# hunt through an expression.
MIN_OBSERVATIONS = 100
MAX_MISSING_PCT = 50.0
MAX_DUPLICATE_PCT = 25.0
MIN_ROUTES = 2
MIN_OBSERVATIONS_PER_CURVE = 2.0


class HistoricalDataAuditService:
    def __init__(self):
        pass

    def run_audit(self, destination: Optional[str] = None) -> Dict[str, Any]:
        """Perform a comprehensive audit of the historical dataset in DB.

        `destination` overrides where the report is written; it defaults to
        `REPORT_PATH`. Tests pass a temporary directory so that a run cannot
        rewrite a tracked file.
        """
        df_raw = db.get_training_dataset()

        if df_raw is None or df_raw.empty:
            report = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_observations": 0,
                "route_coverage_count": 0,
                "distinct_booking_curves": 0,
                "missing_value_percentage": 100.0,
                "duplicate_observation_percentage": 0.0,
                "observations_per_booking_curve_avg": 0.0,
                "observations_per_route_avg": 0.0,
                "feature_completeness_ratio": 0.0,
                "status": "FAIL",
                "failed_bounds": ["total_observations >= 1"],
                "reason": "Database returned no records"
            }
            write_report(report, destination or REPORT_PATH)
            return report

        total_obs = len(df_raw)

        # 1. Route coverage count
        routes = set()
        if "route" in df_raw.columns:
            routes = set(df_raw["route"].dropna().unique())
        elif "origin_code" in df_raw.columns and "destination_code" in df_raw.columns:
            pairs = df_raw["origin_code"].fillna("") + "-" + df_raw["destination_code"].fillna("")
            routes = set(pairs.unique())

        route_coverage_count = len(routes)

        # 2. Missing value percentage
        total_cells = df_raw.shape[0] * df_raw.shape[1]
        missing_cells = df_raw.isna().sum().sum()
        missing_pct = float((missing_cells / max(1, total_cells)) * 100.0)

        # 3. Duplicate observations
        #
        # A duplicate is the same curve observed at the same instant twice. The key
        # is `BOOKING_CURVE_KEYS` plus an observation timestamp, and `dup_pct`
        # gates the status below, so getting it wrong fails a healthy corpus.
        #
        # It was `[origin, destination, airline, flight_number, departure_date,
        # price]`, wrong in two independent ways. It named `flight_number`, which
        # no wired provider publishes, so that component was NULL on every row and
        # every one of a carrier's departures on a route and date collapsed
        # together. And it carried no observation time while carrying `price`, so a
        # fare that held steady across a week of collection — the ordinary shape of
        # a booking curve, and the thing this corpus exists to record — counted
        # every day after the first as a duplicate of the first.
        #
        # `keep=False` is retained: it counts both members of a colliding pair,
        # which is the right census for a report that says "this many rows are
        # involved in duplication" rather than "this many would be dropped".
        ts_cols = [c for c in (ORDERING_TIMESTAMP_KEY, FALLBACK_TIMESTAMP_KEY)
                   if c in df_raw.columns]
        identity_cols = [c for c in BOOKING_CURVE_KEYS if c in df_raw.columns]
        dup_cols = identity_cols + ts_cols[:1]
        # Without the full identity or any timestamp, the question is unanswerable
        # and 0.0 is not an answer to it — but neither is a number computed from a
        # key that pools distinct flights. `duplicate_key` in the report says which
        # columns were compared, and the status gate below now also fails when the
        # identity is incomplete, so this cannot read as a clean bill of health.
        measurable = len(identity_cols) == len(BOOKING_CURVE_KEYS) and bool(ts_cols)
        dupes = df_raw.duplicated(subset=dup_cols, keep=False).sum() if measurable else 0
        dup_pct = float((dupes / max(1, total_obs)) * 100.0)

        # 4. Booking curve density — observations per curve, over the real curve
        # key. `curve_group_columns` returns the subset of BOOKING_CURVE_KEYS the
        # frame actually has; a partial key pools distinct flights into one group
        # and understates the curve count, so the report names which columns it
        # was able to group on rather than implying it grouped on all five.
        group_cols = curve_group_columns(df_raw)
        if group_cols:
            distinct_curves = int(df_raw.groupby(group_cols, dropna=False).ngroups)
        else:
            distinct_curves = 0
        curve_density = float(total_obs / distinct_curves) if distinct_curves else 0.0
        route_density = float(total_obs / max(1, route_coverage_count))

        # 5. Feature completeness ratio
        feature_completeness = float((100.0 - missing_pct) / 100.0)

        # 6. Status. Every figure measured above is consulted, and a breach is
        # named in the report. The previous expression read
        # `"PASS" if total_obs >= 100 and missing_pct <= 50.0 else "WARNING"`,
        # which ignored duplicates, route coverage and density, and had no FAIL
        # branch at all for a non-empty frame.
        failed_bounds = []
        if total_obs < MIN_OBSERVATIONS:
            failed_bounds.append(f"total_observations >= {MIN_OBSERVATIONS} (got {total_obs})")
        if missing_pct > MAX_MISSING_PCT:
            failed_bounds.append(
                f"missing_value_percentage <= {MAX_MISSING_PCT} (got {round(missing_pct, 2)})")
        if dup_pct > MAX_DUPLICATE_PCT:
            failed_bounds.append(
                f"duplicate_observation_percentage <= {MAX_DUPLICATE_PCT} (got {round(dup_pct, 2)})")
        if not measurable:
            # 0.0 duplicates because nothing could be compared is not a pass. Name
            # what is missing so the reader knows whether to apply migration 001 or
            # to look at the loader.
            failed_bounds.append(
                "duplicate_observation_percentage measurable: needs every one of "
                f"{BOOKING_CURVE_KEYS} plus {ORDERING_TIMESTAMP_KEY} or "
                f"{FALLBACK_TIMESTAMP_KEY}; frame has "
                f"{dup_cols or 'none of them'}, so the figure is unmeasured "
                "rather than zero")
        if route_coverage_count < MIN_ROUTES:
            failed_bounds.append(f"route_coverage_count >= {MIN_ROUTES} (got {route_coverage_count})")
        if not group_cols:
            failed_bounds.append(
                "booking curve key present: frame has none of "
                f"{BOOKING_CURVE_KEYS}, so observations cannot be grouped into curves")
        elif curve_density < MIN_OBSERVATIONS_PER_CURVE:
            failed_bounds.append(
                f"observations_per_booking_curve_avg >= {MIN_OBSERVATIONS_PER_CURVE} "
                f"(got {round(curve_density, 2)}) — a curve with one observation "
                "yields no price change")

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_observations": total_obs,
            "route_coverage_count": route_coverage_count,
            "distinct_booking_curves": distinct_curves,
            "booking_curve_key_columns": group_cols,
            "missing_value_percentage": round(missing_pct, 2),
            "duplicate_observation_percentage": round(dup_pct, 2),
            # What "duplicate" was actually computed over, and whether it could be
            # computed at all. Without these two a reader cannot tell a corpus with
            # no duplicates from a frame that had no key to find them by.
            "duplicate_key_columns": dup_cols,
            "duplicate_percentage_measured": measurable,
            "observations_per_booking_curve_avg": round(curve_density, 2),
            "observations_per_route_avg": round(route_density, 2),
            "feature_completeness_ratio": round(feature_completeness, 4),
            "status": "PASS" if not failed_bounds else "FAIL",
            "failed_bounds": failed_bounds,
        }

        write_report(report, destination or REPORT_PATH)
        return report


historical_data_audit_service = HistoricalDataAuditService()
