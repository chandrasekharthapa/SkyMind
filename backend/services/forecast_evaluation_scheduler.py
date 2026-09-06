"""Forecast Evaluation Scheduler — measures a stored forecast against what happened.

This is the only place in the project that could produce an out-of-sample error
figure from realised fares, and until now it produced none: the pending-forecast
query at the top called `.eq()` directly on the table builder with no `.select()`
in between, which raises `AttributeError`, was caught by the surrounding
`except`, and returned 0. The loop below has therefore never executed a single
iteration since it was written.

Repairing that one line on its own would have been worse than leaving it broken,
because the body it guarded computed the wrong quantity in four separate ways:

1. It looked for observations whose `departure_date` equalled
   `forecast_timestamp + horizon` — flights *departing* on the day the horizon
   elapsed, rather than a later observation of the flight the forecast was about.
   The departure date being forecast was not stored at all, so there was nothing
   to match on; `prediction_service` now records it.

2. When that found nothing it fell back to a query carrying no date predicate
   whatsoever — every fare ever recorded on the city pair — under a comment
   claiming a "±1 day" window it did not implement.

3. It then took `min()` of whatever came back and called it the realised price.
   On the fallback path that is the cheapest fare ever seen between two cities,
   which is not a realised price of anything and is guaranteed to make every
   forecast look terrible.

4. `airline` and `flight_number` were read out of the recommendation context and
   never used in either query, so even the primary path pooled every carrier on
   the route.

What replaces it measures the same quantity the model was trained to predict.
The training label is `booking_curve_definition.price_at_horizon`: the earliest
observation *on the same booking curve* at or after `t + horizon`, accepted only
within `lag_tolerance_days(horizon)`. This module resolves the outcome by that
same rule, from that same module, because an error measured against a differently
defined outcome is not the model's error.

A forecast whose outcome window closes with no matching observation is marked
UNEVALUABLE rather than left PENDING. Leaving it pending was an unbounded queue:
every run re-scanned every forecast that could never be resolved.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.database.database import database as db
from backend.domain.provenance import PROVENANCE_IS_FILTERS
from backend.services.booking_curve_definition import (
    BOOKING_CURVE_KEYS,
    MIN_TRAINABLE_HORIZON_DAYS,
    lag_tolerance_days,
    ordering_timestamps,
)

logger = logging.getLogger(__name__)

# One run evaluates at most this many pending forecasts. The table grows by one
# row per published forecast point per prediction, so an unbounded scan is a
# scheduler that gets slower every day it runs.
MAX_FORECASTS_PER_RUN = 500

# Candidate observations fetched per forecast before the window is applied
# precisely. A booking curve is one flight on one departure date, so the true
# count is small; the cap is here so a mislabelled corpus cannot pull the table.
MAX_CANDIDATE_OBSERVATIONS = 500

# Provenance predicate for a fare that may be called "realised". The same two
# conditions `database._PROVENANCE_SQL` applies to the training corpus, for the
# same reason: a synthesised row is not an outcome, and the seeded block that
# `is_synthetic` alone failed to exclude carries `is_live = FALSE`.
#
# Imported rather than restated. This tuple, the SQL predicate, its Supabase
# mirror and `training_eligibility` were four hand-written copies of one rule,
# and the fourth had already lost the `is_live` half.
_REALISED_FARE_FILTERS = PROVENANCE_IS_FILTERS

STATUS_PENDING = "PENDING"
STATUS_COMPLETED = "COMPLETED"
STATUS_UNEVALUABLE = "UNEVALUABLE"


def _parse_utc(value: Any) -> Optional[datetime]:
    """A timestamp as tz-aware UTC, or None if it does not parse.

    Supabase returns ISO strings with an offset; a locally constructed row may be
    naive. Comparing the two raises, and the previous body did exactly that with
    a bare `.replace("Z", "+00:00")` on a value it assumed was a string.
    """
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
    except (TypeError, ValueError):
        return None
    if parsed is pd.NaT or pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


class ForecastEvaluationScheduler:
    def __init__(self, database=None):
        # Injectable so the outcome resolution can be exercised without Supabase.
        self._db = database if database is not None else db

    # ── the outcome ──────────────────────────────────────────────────────────
    def _resolve_outcome(
        self,
        curve: Dict[str, Any],
        target_time: datetime,
        tolerance_days: float,
    ) -> Tuple[Optional[float], Optional[datetime], str]:
        """`(price, observed_at, note)` for the realised fare, or `(None, None, why)`.

        The earliest observation on `curve` whose observation time falls in
        `[target_time, target_time + tolerance_days]` — `price_at_horizon`'s rule,
        applied to one curve instead of a whole frame.

        The window is applied to the timestamp `ordering_timestamps` resolves
        (`search_timestamp`, falling back to `recorded_at`), not to whichever
        column happened to be convenient. The rows are *fetched* on `recorded_at`
        because that is the column PostgREST can filter and the one that is non-null
        on every row, and the fetch window is widened by the tolerance on both sides
        so that a row whose `search_timestamp` is inside the window cannot be missed
        because its `recorded_at` sits outside it. Training and evaluation therefore
        agree on what "observed at" means, which is the class of defect this whole
        module exists downstream of.
        """
        window_end = target_time + timedelta(days=tolerance_days)
        fetch_start = target_time - timedelta(days=tolerance_days)
        fetch_end = window_end + timedelta(days=tolerance_days)

        query = self._db.supabase.table("price_history").select(
            "price,recorded_at,search_timestamp"
        )
        for key in BOOKING_CURVE_KEYS:
            query = query.eq(key, curve[key])
        for column, value in _REALISED_FARE_FILTERS:
            query = query.is_(column, value)
        rows = (
            query.gte("recorded_at", fetch_start.isoformat())
            .lte("recorded_at", fetch_end.isoformat())
            .order("recorded_at")
            .limit(MAX_CANDIDATE_OBSERVATIONS)
            .execute()
        ).data or []

        if not rows:
            return None, None, (
                f"no observation of this curve recorded between "
                f"{fetch_start.isoformat()} and {fetch_end.isoformat()}"
            )

        frame = pd.DataFrame(rows)
        frame["_observed_at"] = ordering_timestamps(frame)
        frame["_price"] = pd.to_numeric(frame.get("price"), errors="coerce")

        in_window = frame[
            frame["_observed_at"].notna()
            & frame["_price"].notna()
            & (frame["_observed_at"] >= pd.Timestamp(target_time))
            & (frame["_observed_at"] <= pd.Timestamp(window_end))
        ]
        if in_window.empty:
            return None, None, (
                f"{len(frame)} observation(s) of this curve exist nearby but none "
                f"falls in [{target_time.isoformat()}, {window_end.isoformat()}], "
                f"the window the training label uses for a {tolerance_days:.2f}-day "
                f"tolerance"
            )

        # Earliest in the window, matching the label's "first observation at or
        # after t + horizon". Not the minimum price: the cheapest fare in the
        # window is a different quantity from the fare that was there when the
        # horizon elapsed, and substituting one for the other was defect 3 above.
        first = in_window.sort_values("_observed_at").iloc[0]
        return (
            float(first["_price"]),
            first["_observed_at"].to_pydatetime(),
            "",
        )

    # ── the loop ─────────────────────────────────────────────────────────────
    def _load_pending(self) -> List[Dict[str, Any]]:
        """Pending forecasts, oldest first.

        The `.select("*")` is the repair: this read
        `db.supabase.table("forecast_store").eq("status", "PENDING")`, and
        `.eq` does not exist on a table builder, so every run raised
        `AttributeError` and returned 0.
        """
        res = (
            self._db.supabase.table("forecast_store")
            .select("*")
            .eq("status", STATUS_PENDING)
            .order("forecast_timestamp")
            .limit(MAX_FORECASTS_PER_RUN)
            .execute()
        )
        return res.data or []

    def _curve_from(self, forecast: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        """The five-component booking curve the forecast was about, or why not.

        A partial key is not a curve: matching on four of the five components
        pools every flight sharing them, and the "realised fare" becomes another
        aircraft's. `booking_curve_definition` states the same rule for the
        training label, which refuses a frame missing any key rather than
        degrading.
        """
        rec = forecast.get("recommendation") or {}
        if not isinstance(rec, dict):
            return None, f"recommendation context is {type(rec).__name__}, not an object"

        curve = {
            "origin_code": rec.get("origin_code") or rec.get("origin"),
            "destination_code": rec.get("destination_code") or rec.get("destination"),
            "airline_code": rec.get("airline_code") or rec.get("airline"),
            # The fifth component was `flight_number` until 2026-09-03. The
            # provider does not publish one, so it was None on every stored
            # forecast and this function rejected all of them as unidentifiable.
            # `departure_time` is the identity that exists; see the note above
            # `BOOKING_CURVE_KEYS`. Forecasts written before that change carry no
            # `departure_time` and are still correctly refused here — they really
            # cannot be matched to an outcome, and guessing which of a carrier's
            # departures they meant is the defect this docstring describes.
            "departure_time": rec.get("departure_time"),
            "departure_date": rec.get("departure_date"),
        }
        missing = [k for k in BOOKING_CURVE_KEYS
                   if curve.get(k) is None or str(curve[k]).strip() == ""]
        if missing:
            return None, (
                f"recommendation context names no {', '.join(missing)}, so the "
                f"booking curve this forecast was about cannot be identified"
            )
        return {k: str(v).strip() for k, v in curve.items()}, ""

    def _finish(self, forecast_row_id: Any, patch: Dict[str, Any]) -> None:
        self._db.supabase.table("forecast_store").update(patch).eq(
            "id", forecast_row_id).execute()

    def _mark_unevaluable(self, forecast: Dict[str, Any], note: str, now: datetime) -> None:
        """Take a forecast out of the pending queue, recording why.

        It used to `continue`, leaving the row PENDING for ever — so every
        subsequent run re-read and re-failed it, and the queue only ever grew.
        No `actual_price` and no `evaluation_metrics` are written: there is no
        measured outcome, and writing a placeholder is how a fabricated error
        figure would enter the table.
        """
        logger.warning("Forecast %s is unevaluable: %s", forecast.get("forecast_id"), note)
        self._finish(forecast.get("id"), {
            "status": STATUS_UNEVALUABLE,
            "evaluated_at": now.isoformat(),
            "evaluation_metrics": {"unevaluable_reason": note},
        })

    async def evaluate_pending_forecasts(self) -> int:
        """Evaluate every pending forecast whose outcome window has closed.

        Returns the number of forecasts for which a realised fare was found and an
        error recorded. Forecasts retired as unevaluable are counted separately and
        logged, because a run that resolves nothing and a run that finds nothing to
        resolve are different states.
        """
        logger.info("[ForecastEvaluationScheduler] Querying PENDING forecasts...")
        try:
            pending = self._load_pending()
        except Exception as exc:
            logger.error(
                "[ForecastEvaluationScheduler] Failed to query pending forecasts: %s",
                exc, exc_info=True)
            return 0

        if not pending:
            logger.info("[ForecastEvaluationScheduler] No pending forecasts found.")
            return 0

        now = datetime.now(timezone.utc)
        evaluated = 0
        retired = 0
        waiting = 0

        for forecast in pending:
            try:
                outcome = self._evaluate_one(forecast, now)
            except Exception as exc:
                # Recorded with a traceback and left PENDING: an exception here is
                # a bug in this module or a transport failure, and neither is
                # evidence about the forecast.
                logger.error("Error evaluating pending forecast %s: %s",
                             forecast.get("forecast_id"), exc, exc_info=True)
                continue
            if outcome == "evaluated":
                evaluated += 1
            elif outcome == "retired":
                retired += 1
            else:
                waiting += 1

        logger.info(
            "[ForecastEvaluationScheduler] Finished: %d evaluated, %d retired as "
            "unevaluable, %d still waiting for their horizon to elapse (of %d "
            "pending rows read, cap %d).",
            evaluated, retired, waiting, len(pending), MAX_FORECASTS_PER_RUN)
        return evaluated

    def _evaluate_one(self, forecast: Dict[str, Any], now: datetime) -> str:
        """`"evaluated"`, `"retired"` or `"waiting"` for one pending forecast."""
        forecast_time = _parse_utc(forecast.get("forecast_timestamp"))
        if forecast_time is None:
            self._mark_unevaluable(
                forecast,
                f"forecast_timestamp {forecast.get('forecast_timestamp')!r} does not "
                f"parse as a timestamp, so the horizon cannot be resolved to a date",
                now)
            return "retired"

        horizon = forecast.get("prediction_horizon")
        try:
            horizon = int(horizon)
        except (TypeError, ValueError):
            horizon = None
        if horizon is None or horizon < MIN_TRAINABLE_HORIZON_DAYS:
            # Was `int(f.get("prediction_horizon", 0))`: a row recording no horizon
            # was evaluated as a forecast of the present instant, whose "outcome"
            # is the observation the forecast was made from.
            self._mark_unevaluable(
                forecast,
                f"prediction_horizon {forecast.get('prediction_horizon')!r} is not a "
                f"whole number of days >= {MIN_TRAINABLE_HORIZON_DAYS}, so there is no "
                f"future fare it is a forecast of",
                now)
            return "retired"

        forecast_price = pd.to_numeric(forecast.get("forecast_price"), errors="coerce")
        if pd.isna(forecast_price) or float(forecast_price) <= 0:
            # Was `float(f.get("forecast_price", 0.0))`: a row with no recorded
            # forecast became a ₹0 forecast, and its "error" the whole actual fare.
            self._mark_unevaluable(
                forecast,
                f"forecast_price {forecast.get('forecast_price')!r} is not a positive "
                f"fare, so there is no prediction to score",
                now)
            return "retired"
        forecast_price = float(forecast_price)

        tolerance = lag_tolerance_days(horizon)
        target_time = forecast_time + timedelta(days=horizon)
        window_end = target_time + timedelta(days=tolerance)

        if now < window_end:
            # The horizon may have elapsed, but an observation that would satisfy
            # the window can still arrive. Retiring it now would record "no
            # outcome" for a forecast whose outcome has not finished happening.
            return "waiting"

        curve, why = self._curve_from(forecast)
        if curve is None:
            self._mark_unevaluable(forecast, why, now)
            return "retired"

        actual_price, observed_at, note = self._resolve_outcome(
            curve, target_time, tolerance)
        if actual_price is None:
            self._mark_unevaluable(forecast, note, now)
            return "retired"

        error_val = forecast_price - actual_price
        metrics: Dict[str, Any] = {
            "error": round(error_val, 2),
            "abs_error": round(abs(error_val), 2),
            # The denominator is the realised fare itself. It used to be
            # `max(actual_price, 1.0)`, which turns a non-positive actual into a
            # percentage of ₹1 — the same defect the training MAPE had, where one
            # zero-fare row produced 200,000%. A non-positive fare has no
            # percentage error, so the figure is null and the count says why.
            "percentage_error": (round(abs(error_val) / actual_price * 100.0, 2)
                                 if actual_price > 0 else None),
            "forecast_price": round(forecast_price, 2),
            "horizon_days": horizon,
            # The provenance of the number, so a reader can check it rather than
            # trust it: which instant the outcome was owed at, how wide a window
            # was accepted, and when the matched fare was actually observed.
            "target_time": target_time.isoformat(),
            "window_end": window_end.isoformat(),
            "observed_at": observed_at.isoformat() if observed_at else None,
            "observation_rule": (
                "earliest observation on the same booking curve at or after "
                "forecast_timestamp + horizon, within lag_tolerance_days(horizon) "
                "— the definition backend.services.booking_curve_definition."
                "price_at_horizon uses for the training label"
            ),
        }
        if metrics["percentage_error"] is None:
            metrics["percentage_error_unavailable"] = (
                f"realised fare {actual_price} is not positive")

        self._finish(forecast.get("id"), {
            "actual_price": actual_price,
            "status": STATUS_COMPLETED,
            "evaluated_at": now.isoformat(),
            "evaluation_metrics": metrics,
        })
        logger.info(
            "Evaluated forecast %s (%dd): forecast=%.2f actual=%.2f error=%+.2f "
            "observed_at=%s",
            forecast.get("forecast_id"), horizon, forecast_price, actual_price,
            error_val, observed_at.isoformat() if observed_at else "?")
        return "evaluated"


forecast_evaluation_scheduler = ForecastEvaluationScheduler()
