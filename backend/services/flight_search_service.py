"""Flight Search Orchestration Service.

Combines the Flight Repository, MCP Flight Search client, Flight Normalizer,
ML enrichment, and Recommendation Engine into a unified business logic flow.
"""

import time
import logging
from datetime import date, datetime, timezone
from typing import List, Dict, Any, Optional

from backend.database.flight_repository import flight_repository
from backend.services.flight_data_service import (
    flight_data_service,
    STATUS_OK,
    STATUS_ERROR,
)
from backend.services.flight_normalizer import FlightNormalizer, NormalizedFlight
from backend.services.flight_formatter import RecommendationFormatter
from backend.services.recommendation_engine import RecommendationEngine
from backend.services.flight_presentation import FlightSearchPresentation, AirportPresentation
from backend.services.ingestion_controller import MarketDataController
from backend.ml.price_model import get_predictor, IMPLAUSIBLE_FARE_FLOOR
from backend.utils.resilience import mcp_breaker, database_breaker
from backend.utils.observability import ObservabilityTracker

logger = logging.getLogger(__name__)


class _ProviderFailure(Exception):
    """Carries a transport failure the provider described, as an exception.

    The transport reports failure by *returning* ``{"status": "error", ...}``,
    but CircuitBreaker.run() decides success by whether its callable raised. The
    two contracts are incompatible: left alone, every failed scrape was recorded
    as a success and the breaker could not open. Raising this inside the guarded
    callable makes the breaker's accounting truthful while keeping the structured
    result — its status, error, error_kind and attempt count — available to the
    caller, which unwraps it immediately. It is private to this module and never
    escapes past the call site.
    """

    def __init__(self, result: Dict[str, Any]):
        super().__init__(result.get("error") or "provider failure")
        self.result = result


class FlightSearchService:
    def __init__(self):
        self.repository = flight_repository

    def _model(self):
        try:
            return get_predictor()
        except Exception as e:
            # Callers treat None as "no ML available" and fall back, so this
            # must be logged or a broken predictor looks like an untrained one.
            logger.warning(f"Price predictor unavailable: {type(e).__name__}: {e}")
            return None

    @staticmethod
    def _build_recommendation(cheapest, any_flights: bool):
        """Assess the cheapest fare, or decline to assess it.

        This lived inline in `search_flights` and could not be exercised without
        standing up a provider, a database and a model, which is why its defect
        survived: the branch was chosen by `cheapest.metadata` — the presence of
        the metadata *dict*, not the presence of a prediction. `_enrich_with_ml`
        always leaves something in that dict, including the "no price forecast
        available" advice it writes when the model is untrained, declined, or
        raised. On exactly those paths the guard passed, and
        `.get("ai_price", cheapest.price)` handed the listed fare to
        `RecommendationFormatter.format(price, price)`, whose neutral branch
        returns "FAIR PRICE" / "Current price is within normal limits." /
        "STABLE". A verdict on a fare, issued because there was no verdict —
        and `unavailable()` below, which exists for this case, was unreachable
        whenever enrichment had run at all.

        Ask for the prediction, not for the envelope it would have arrived in.
        """
        meta = getattr(cheapest, "metadata", None) or {} if cheapest else {}
        predicted = meta.get("ai_price")
        if predicted is not None:
            return RecommendationFormatter.format(float(predicted), cheapest.price)
        if not any_flights:
            return RecommendationFormatter.unavailable(
                "No flights were available for this route, so no booking advice can be given."
            )
        # A flight exists but carries no predicted price to compare its fare
        # against. This was `format(1.0, 1.0)`, which returned "FAIR PRICE" /
        # "STABLE" — a verdict derived from two placeholder constants.
        return RecommendationFormatter.unavailable(
            "No price prediction is available for this route yet, so the fare cannot be assessed."
        )

    def _enrich_with_ml(self, flights: List[NormalizedFlight], origin: str, destination: str, departure_date: str) -> List[NormalizedFlight]:
        """Add AI price prediction and recommendation to each normalized flight's metadata."""
        import numpy as np

        model = self._model()
        if not model or not model._trained:
            # No trained model: say so, and do not invent a prediction.
            #
            # This block used to set ai_price = f.price, which presents the
            # listed fare back to the user as an AI price prediction, and
            # advice = "Current price is fair", which is a valuation no model
            # produced. ai_price is now absent (the field is optional), and
            # ml_available records why, so a caller can tell "the model says
            # this price is fine" apart from "there is no model".
            logger.info(
                "ML enrichment skipped for %s-%s: %s",
                origin, destination,
                "no predictor" if not model else "predictor not trained",
            )
            for f in flights:
                if not hasattr(f, "metadata") or f.metadata is None:
                    f.metadata = {}
                f.metadata.pop("ai_price", None)
                f.metadata["ml_available"] = False
                f.metadata["recommendation"] = "MONITOR"
                f.metadata["trend"] = "UNKNOWN"
                f.metadata["decision"] = "UNKNOWN"
                f.metadata["advice"] = (
                    "No price forecast available: the model is not trained yet."
                )
            return flights

        # Raw observation history for this route and date. The per-flight
        # day-based price changes are computed inside the loop below by
        # `price_changes_from_records`, which is the same as-of lag the training
        # path uses.
        #
        # This block used to average the prices observed in the last 1 and 3 days
        # across the whole route and subtract the average from each fare,
        # publishing the two results as `price_change_1d` and `price_change_3d` —
        # names that mean "difference from the price n days ago" everywhere else
        # in the system, and the feature carrying the model's largest importance.
        # A difference from a mean is a different quantity: on a steadily rising
        # curve it reports roughly half the true change, and because the history
        # query filters on route and date only, the mean pooled every airline and
        # flight number together. The row limit is raised from 50 to 200 because
        # a per-flight curve is now selected out of the result rather than the
        # whole route being averaged.
        from backend.services.booking_curve_definition import price_changes_from_records

        db_records: List[Dict[str, Any]] = []
        try:
            db_records = self.repository.get_price_history_cache(
                origin, destination, departure_date, 200
            ) or []
        except Exception as e:
            logger.warning(
                "Price history unavailable for %s-%s %s (%s); day-based price "
                "changes are unknown for this batch.",
                origin, destination, departure_date, e,
            )
        now_utc = datetime.now(timezone.utc)

        try:
            dep_date_obj = datetime.strptime(departure_date, "%Y-%m-%d").date()
            days_until_dep = max(0, (dep_date_obj - date.today()).days)

            for f in flights:
                try:
                    # Deterministically parse departure hour from segment timestamp
                    hour_of_day = np.nan
                    is_peak_hour = np.nan
                    if f.itineraries and f.itineraries[0].segments:
                        dep_time_str = f.itineraries[0].segments[0].departure_time
                        if dep_time_str and "T" in dep_time_str:
                            try:
                                hour_part = dep_time_str.split("T")[1]
                                hour_of_day = float(hour_part.split(":")[0])
                                is_peak_hour = 1.0 if hour_of_day in [7, 8, 9, 10, 17, 18, 19, 20] else 0.0
                            except Exception as hour_err:
                                # Leaving both NaN is correct — the model must
                                # not be fed a guessed departure hour — but an
                                # unlogged skip hides a provider format change
                                # that would degrade every prediction.
                                logger.warning(
                                    "Unreadable departure_time %r (%s); hour_of_day and "
                                    "is_peak_hour left unknown", dep_time_str, hour_err,
                                )

                    # Day-based price changes on THIS flight's booking curve,
                    # via the shared as-of lag. NaN when the flight has no
                    # comparable earlier observation — which is what the model is
                    # now trained on, since the training lags are NaN in exactly
                    # the same circumstance. Filling 0.0 here would tell the model
                    # the fare had not moved.
                    changes = price_changes_from_records(
                        db_records,
                        curve={
                            "origin_code": origin,
                            "destination_code": destination,
                            "airline_code": f.primary_airline,
                            "flight_number": getattr(f, "flight_number", None),
                            "departure_date": departure_date,
                        },
                        current_price=f.price,
                        current_time=now_utc,
                        lag_days=(1, 3),
                    )
                    price_change_1d = changes["price_change_1d"]
                    price_change_3d = changes["price_change_3d"]

                    predicted = model.predict({
                        "origin_code": origin,
                        "destination_code": destination,
                        "airline_code": f.primary_airline,
                        "days_until_dep": days_until_dep,
                        "day_of_week": dep_date_obj.weekday(),
                        "month": dep_date_obj.month,
                        "week_of_year": dep_date_obj.isocalendar()[1],
                        "hour_of_day": hour_of_day,
                        "is_peak_hour": is_peak_hour,
                        "is_live": True,
                        "seats_available": float(f.seats_available) if f.seats_available is not None else np.nan,
                        "price_change_1d": price_change_1d,
                        "price_change_3d": price_change_3d,
                        "demand_score": np.nan,
                        "seasonality_factor": np.nan,
                    })

                    predicted = float(predicted)

                    if not hasattr(f, "metadata") or f.metadata is None:
                        f.metadata = {}

                    # Was `predicted = max(2800.0, min(float(predicted), 55000.0))`.
                    #
                    # A model that returned ₹1,200 was displayed as ₹2,800 beside
                    # `ml_available: True`, so a broken model was indistinguishable
                    # on screen from a working one. Worse, the rewritten number then
                    # drove the 1.12 / 0.88 comparison below, so the *advice* was
                    # derived from a figure the model never produced. The display was
                    # only where it showed; deriving a recommendation from a value
                    # the caller invented is the defect.
                    #
                    # An implausible prediction is now treated exactly as one that
                    # raised: not served. The threshold is `IMPLAUSIBLE_FARE_FLOOR`,
                    # the constant `price_model.predict` already logs against, rather
                    # than a second local 2800 that nothing else in the system knows.
                    #
                    # There is deliberately no ceiling. 55000 was measured nowhere —
                    # no artifact's metadata records the fare range it was trained on
                    # — and trimming a runaway ₹900,000 prediction to ₹55,000 makes a
                    # broken model look plausible, which is the worse failure. A high
                    # prediction is published as itself, where it is visibly wrong.
                    if predicted < IMPLAUSIBLE_FARE_FLOOR:
                        logger.warning(
                            "Model returned ₹%.2f for %s %s (%s-%s %s), below the "
                            "₹%.0f plausibility floor. Serving no prediction for this "
                            "flight rather than raising the value to the floor.",
                            predicted,
                            getattr(f, "primary_airline", "?"),
                            getattr(f, "flight_number", "?"),
                            origin, destination, departure_date,
                            IMPLAUSIBLE_FARE_FLOOR,
                        )
                        f.metadata.pop("ai_price", None)
                        f.metadata["ml_available"] = False
                        f.metadata["recommendation"] = "MONITOR"
                        f.metadata["trend"] = "UNKNOWN"
                        f.metadata["decision"] = "UNKNOWN"
                        f.metadata["advice"] = (
                            "No price forecast available: the model's output for this "
                            "flight was outside the plausible fare range."
                        )
                        continue

                    f.metadata["ai_price"] = round(predicted)
                    f.metadata["ml_available"] = True

                    if predicted > f.price * 1.12:
                        f.metadata["recommendation"] = "BOOK NOW"
                        f.metadata["trend"] = "INCREASING"
                        f.metadata["decision"] = "BUY NOW"
                        f.metadata["advice"] = "Prices expected to rise — lock in this fare."
                    elif predicted < f.price * 0.88:
                        f.metadata["recommendation"] = "WAIT"
                        f.metadata["trend"] = "DECREASING"
                        f.metadata["decision"] = "WAIT"
                        f.metadata["advice"] = "Model predicts a price drop soon."
                    else:
                        f.metadata["recommendation"] = "FAIR PRICE"
                        f.metadata["trend"] = "STABLE"
                        f.metadata["decision"] = "FAIR"
                        f.metadata["advice"] = "Current price is within normal range."

                except Exception as exc:
                    # A prediction that raised is not a prediction. This handler
                    # used to echo the listed fare back as ai_price and assert
                    # "Price is stable.", so a per-flight model failure was
                    # indistinguishable on screen from a model that had run and
                    # found the fare fair. Log at warning (a swallowed failure
                    # at debug level is invisible in production) and record the
                    # absence instead.
                    logger.warning(
                        "ML enrichment failed for %s %s: %s: %s",
                        getattr(f, "airline_code", "?"), getattr(f, "flight_number", "?"),
                        type(exc).__name__, exc,
                    )
                    if not hasattr(f, "metadata") or f.metadata is None:
                        f.metadata = {}
                    f.metadata.pop("ai_price", None)
                    f.metadata["ml_available"] = False
                    f.metadata["recommendation"] = "MONITOR"
                    f.metadata["trend"] = "UNKNOWN"
                    f.metadata["decision"] = "UNKNOWN"
                    f.metadata["advice"] = "No price forecast available for this flight."
        except Exception as exc:
            logger.warning(f"ML enrichment batch error: {exc}")

        return flights

    async def search(
        self,
        origin_iata: str,
        destination_iata: str,
        departure_date: str,
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
        cabin_class: str = "ECONOMY",
        max_results: int = 100,
        return_date: Optional[str] = None,
        sorting: str = "price"
    ) -> FlightSearchPresentation:
        """Execute flight search E2E flow."""
        import uuid
        from backend.services.historical_data_service import historical_data_service
        from backend.services.booking_curve_definition import (
            BOOKING_CURVE_KEYS,
            deduplicate_observation_batch,
        )
        from backend.domain.provenance import screen_observation_fares

        start_time = time.time()
        unique_flights = []
        data_source = "UNKNOWN"
        search_status = "success"
        search_id = str(uuid.uuid4())
        search_session_id = str(uuid.uuid4())
        search_timestamp = datetime.now(timezone.utc).isoformat()
        snapshot_id = str(uuid.uuid4())
        recorded_at_str = search_timestamp

        # Provenance and persistence facts, reported rather than assumed. Every one
        # of these was previously either absent from the response or guessed:
        # `data_source` was initialised to "LIVE_MAKEMYTRIP_MCP" before the provider
        # had been called, so an empty result was relabelled a cache read and a
        # crash was relabelled "error recovery" — labels inferred from control flow
        # rather than from what the transport reported. And `metadata["count"]` was
        # the number of flights *displayed*, which the scheduler and the UI both
        # read as though it were the number of observations *stored*.
        provider_status: Optional[str] = None
        provider_error: Optional[str] = None
        provider_error_kind: Optional[str] = None
        provider_attempts: int = 0
        rows_submitted: int = 0
        rows_persisted: Optional[int] = None
        persistence_error: Optional[str] = None
        # Rows the provider returned twice for the same flight in this one search,
        # and which `deduplicate_observation_batch` collapsed before submission.
        # Reported rather than discarded quietly: it is the only signal anywhere in
        # the project that the scraper is emitting duplicate cards, and after
        # migration 001 STEP 8b it is the difference between a stored batch and a
        # rejected one.
        provider_duplicate_rows: int = 0
        # Rows this search observed but refused to store: a fare quoted in another
        # currency, one whose currency the provider did not state, or one outside
        # the fare window the loaders apply. Reported for the same reason as the
        # line above — it is not a database fault and must not be read as one, but a
        # collection run losing rows to a provider serving dollars is exactly the
        # kind of silent shortfall this field exists to make visible.
        refused_rows: int = 0
        refused_currencies: Dict[str, int] = {}
        # Rows stored without a complete booking-curve identity — in practice rows
        # carrying no `departure_time`. They are legitimate market observations and
        # the database accepts them, but `_price_at_offset` excludes them from the
        # label join on both sides, so no number of them ever makes the corpus
        # trainable. `deduplicate_observation_batch` has always counted them (its
        # `unindexable` field, whose own comment calls them "exactly the rows that
        # can never be labelled") and this call site has always thrown the count
        # away, which is how a collection run storing nothing but unlabellable rows
        # reported itself as a clean success.
        unidentified_rows: int = 0

        try:
            # 1. Fetch live flights via flight_data_service MCP tool protected by mcp_breaker
            ObservabilityTracker.record_mcp_call()

            async def _guarded_transport() -> Dict[str, Any]:
                """Call the transport and raise on a tagged failure.

                CircuitBreaker.run() decides success by whether the callable raised.
                search_flights() does not raise — it returns status="error" — so the
                breaker called record_success() after every failed scrape, zeroing
                the failure count, and could never trip no matter how long the
                provider stayed down. Recording the failure *after* run() returns
                does not help either: the next call's record_success() resets it
                first, so the count oscillates between 0 and 1 forever. Raising from
                inside the guarded callable is what makes the accounting correct;
                the structured result is carried on the exception so nothing is lost.
                """
                r = await flight_data_service.search_flights(
                    origin=origin_iata,
                    destination=destination_iata,
                    target_date=departure_date,
                    adults=adults,
                    children=children,
                    infants=infants,
                    cabin_class=cabin_class,
                    max_results=max_results,
                    return_date=return_date,
                    currency="INR",
                )
                if not isinstance(r, dict) or r.get("status") is None:
                    # A transport that answers without a status is a transport we
                    # cannot vouch for. Treat it as broken, not as an empty market.
                    raise _ProviderFailure({
                        "data": [],
                        "status": STATUS_ERROR,
                        "error": f"transport returned {type(r).__name__} without a status",
                        "error_kind": "contract",
                        "attempts": 0,
                    })
                if r.get("status") == STATUS_ERROR:
                    raise _ProviderFailure(r)
                return r

            try:
                res = await mcp_breaker.run(_guarded_transport)
            except _ProviderFailure as pf:
                # A failure the transport described, as opposed to an unknown crash.
                res = pf.result

            mcp_flights = res.get("data") or []
            provider_status = res.get("status")
            provider_error = res.get("error")
            provider_error_kind = res.get("error_kind")
            provider_attempts = int(res.get("attempts") or 0)

            if provider_status == STATUS_ERROR:
                ObservabilityTracker.record_error("mcp_failure")
                logger.error(
                    f"Live MCP search failed [{provider_error_kind}] after "
                    f"{provider_attempts} attempt(s): {provider_error}"
                )

            # 2. Fall back to the DB cache when the provider gave us nothing usable.
            if provider_status != STATUS_OK or not mcp_flights:
                if provider_status == STATUS_ERROR:
                    # The distinction this whole result type exists for: the cache is
                    # being read because the provider *broke*, not because the route
                    # is quiet. Downstream (and the user) are told which.
                    data_source = f"DB_FALLBACK (PROVIDER ERROR: {provider_error_kind})"
                    search_status = "degraded"
                else:
                    logger.info("Live MCP search returned no flights for this route. Falling back to DB cache.")
                    data_source = "DB_FALLBACK (NO LIVE RESULTS)"
                ObservabilityTracker.record_cache_hit()

                # DB retrieval protected by database_breaker
                db_results = await database_breaker.run(
                    self.repository.get_price_history_cache,
                    origin=origin_iata,
                    destination=destination_iata,
                    departure_date=departure_date,
                    max_results=max_results
                )
                for db_flight in db_results:
                    norm = FlightNormalizer.normalize_db_flight(db_flight, origin_iata, destination_iata, departure_date)
                    if norm:
                        unique_flights.append(norm)
            else:
                # The transport is the Google Flights scraper — `flight_data_service`
                # → `mcp_client` → `india-flight-mcp/src/mcp/stdio_server.js` →
                # `providers/GoogleFlightsProvider.js`, which navigates
                # `google.com/travel/flights`. This label read "LIVE_MAKEMYTRIP_MCP",
                # and it is passed straight to `format_payload` as `provider` below,
                # which now also derives `data_source` from it — so both provenance
                # columns on every stored row named a provider this code has never
                # called. `MakeMyTripProvider.js` sat unwired in that directory until
                # 2026-09-03, when it was deleted; Google Flights is now the only
                # source, so this is the only string this branch can produce. Rows
                # written before the relabel still carry the old one; no query
                # anywhere filters on the column.
                data_source = "LIVE_GOOGLE_FLIGHTS_MCP"
                # Ingest live search results to DB cache asynchronously
                try:
                    dep_date_obj = datetime.strptime(departure_date, "%Y-%m-%d").date()
                    days_until_dep = max(0, (dep_date_obj - date.today()).days)
                    db_payloads = []
                    for flight in mcp_flights:
                        price = float(flight.get("price", 0.0))
                        if price <= 0:
                            continue
                        carrier = flight.get("primary_airline") or flight.get("airline_code") or "UNKNOWN"
                        fl_num = flight.get("flight_number")  # None if absent, zero synthetic defaults
                        
                        duration = flight.get("duration")
                        stops = flight.get("stops")
                        terminal = flight.get("terminal")
                        
                        seats = flight.get("seats")
                        if seats is not None:
                            try:
                                seats = int(seats)
                            except (ValueError, TypeError):
                                seats = None

                        # The provider reports the departure instant either at the
                        # top level or on the first segment, depending on which
                        # shape the transport returned. Reading both is what makes
                        # `hour_of_day` and `is_peak_hour` computable from
                        # price_history at training time; without it they are NaN
                        # for every stored row while the serving path supplies
                        # them, which is a feature the model can only ever use in
                        # production.
                        dep_time_raw = flight.get("departure_time")
                        if not dep_time_raw:
                            itins = flight.get("itineraries") or []
                            if itins:
                                segs = (itins[0] or {}).get("segments") or []
                                if segs:
                                    dep_time_raw = (segs[0] or {}).get("departure_time")

                        payload = MarketDataController.format_payload(
                            origin_code=origin_iata,
                            destination_code=destination_iata,
                            airline_code=carrier,
                            price=price,
                            departure_date=departure_date,
                            days_until_dep=days_until_dep,
                            seats_available=seats,
                            flight_number=fl_num,
                            departure_time=dep_time_raw,
                            cabin_class=cabin_class,
                            # What the provider quoted, not what we hope it quoted.
                            # This argument was simply not passed, and the parameter
                            # defaulted to "INR", so a page Google served in dollars
                            # was stored as rupees — the 156 rows at ₹58–₹105 on
                            # 2026-07-19. Absent here means absent: the row is refused
                            # downstream rather than labelled with a guess.
                            currency=flight.get("currency"),
                            provider=data_source,
                            search_id=search_id,
                            search_session_id=search_session_id,
                            search_timestamp=search_timestamp,
                            snapshot_id=snapshot_id,
                            duration=duration,
                            stops=stops,
                            terminal=terminal,
                            recorded_at=recorded_at_str
                        )
                        db_payload = MarketDataController.get_db_payload(payload)
                        db_payloads.append(db_payload)
                        
                    if db_payloads:
                        # Screened and de-duplicated here, not only inside
                        # `insert_observations`, so `rows_submitted` below counts rows
                        # actually submitted. Leaving it as the pre-collapse length
                        # would make every batch containing a duplicated provider card
                        # report `persistence_error: submitted 20, database persisted
                        # 19` — a database fault where there was none, on the one field
                        # the 2026-08 fix pass added specifically so that number could
                        # be trusted. The same argument applies to a refused fare. The
                        # calls in `insert_observations` stay as the guarantee for any
                        # other caller; running either twice is a no-op.
                        #
                        # Screen first: the de-duplicator keeps the cheapest row in an
                        # identity group, so a group holding one dollar quote and one
                        # rupee quote for the same flight would collapse to the dollar
                        # row and then lose it.
                        db_payloads, screen = screen_observation_fares(db_payloads)
                        refused_rows = screen["dropped"]
                        refused_currencies = dict(screen["currencies_seen"])
                        if refused_rows:
                            logger.error(
                                "Refused %d of %d observation(s) for %s-%s on %s: "
                                "%d foreign currency, %d unreadable currency, "
                                "%d outside the fare window. Currencies seen: %s.",
                                refused_rows, screen["submitted"], origin_iata,
                                destination_iata, departure_date,
                                screen["dropped_foreign_currency"],
                                screen["dropped_unreadable_currency"],
                                screen["dropped_implausible_fare"],
                                screen["currencies_seen"] or "none readable",
                            )
                        db_payloads, dedup = deduplicate_observation_batch(db_payloads)
                        provider_duplicate_rows = dedup["dropped"]
                        unidentified_rows = dedup["unindexable"]
                        if unidentified_rows:
                            logger.warning(
                                "%d of %d observation(s) for %s-%s on %s carry an incomplete "
                                "booking-curve identity (%s) and will be stored but never "
                                "labelled; the provider gave no departure time for them.",
                                unidentified_rows, dedup["submitted"], origin_iata,
                                destination_iata, departure_date, ", ".join(BOOKING_CURVE_KEYS),
                            )
                        if provider_duplicate_rows:
                            logger.warning(
                                "Provider returned %d duplicate observation(s) for %s-%s on %s "
                                "(%d identity group(s), %d disagreeing on price); collapsed to %d.",
                                provider_duplicate_rows, origin_iata, destination_iata,
                                departure_date, dedup["groups_collapsed"],
                                dedup["groups_disagreeing_on_price"], dedup["kept"],
                            )
                        rows_submitted = len(db_payloads)
                        # The return value used to be discarded and the exception
                        # swallowed at warning level, so a search whose observations
                        # never reached the database was reported to the caller as an
                        # unqualified success. Both are now recorded.
                        rows_persisted = historical_data_service.insert_observations(db_payloads)
                        if rows_persisted == -1:
                            persistence_error = "database acknowledged no rows; persisted count unknown"
                            logger.error(f"Ingest of {rows_submitted} observation(s) unconfirmed: {persistence_error}")
                        elif rows_persisted != rows_submitted:
                            persistence_error = (
                                f"submitted {rows_submitted} observation(s), "
                                f"database persisted {rows_persisted}"
                            )
                            logger.error(persistence_error)
                except Exception as ingest_err:
                    persistence_error = f"{type(ingest_err).__name__}: {ingest_err}"
                    ObservabilityTracker.record_error("ingest_failure")
                    logger.error(
                        f"Failed to ingest {rows_submitted or len(mcp_flights)} search observation(s) "
                        f"into the DB cache: {ingest_err}",
                        exc_info=True,
                    )

                for flight in mcp_flights:
                    norm = FlightNormalizer.normalize_mcp_flight(flight, origin_iata, destination_iata, departure_date, cabin_class)
                    if norm:
                        unique_flights.append(norm)

        except Exception as mcp_err:
            logger.error(f"MCP search service invocation error: {mcp_err}", exc_info=True)
            ObservabilityTracker.record_error("mcp_failure")
            search_status = "degraded"
            # This branch is now only reached when the orchestration itself raised —
            # the breaker being OPEN, or a genuine bug here. The transport's own
            # failures no longer arrive as exceptions; they arrive tagged.
            if provider_status is None:
                provider_status = STATUS_ERROR
                provider_error_kind = (
                    "breaker_open" if type(mcp_err).__name__ == "CircuitBreakerOpenException"
                    else "orchestration"
                )
                provider_error = f"{type(mcp_err).__name__}: {mcp_err}"

            # Secure endpoint: fail fast by falling back to DB cache if MCP crashed
            data_source = f"DB_FALLBACK (PROVIDER ERROR: {provider_error_kind})"
            ObservabilityTracker.record_cache_hit()
            try:
                db_results = await database_breaker.run(
                    self.repository.get_price_history_cache,
                    origin=origin_iata,
                    destination=destination_iata,
                    departure_date=departure_date,
                    max_results=max_results
                )
                for db_flight in db_results:
                    norm = FlightNormalizer.normalize_db_flight(db_flight, origin_iata, destination_iata, departure_date)
                    if norm:
                        unique_flights.append(norm)
            except Exception as db_err:
                logger.error(f"Fallback DB cache search also failed: {db_err}")
                ObservabilityTracker.record_error("db_failure")
                search_status = "failed"

        # 3. Deduplicate
        unique_flights = FlightNormalizer.deduplicate_flights(unique_flights)

        # 4. ML Enrichment
        unique_flights = self._enrich_with_ml(unique_flights, origin_iata, destination_iata, departure_date)

        # 5. Highlights Identification (Cheapest, Fastest, Best Value)
        cheapest, fastest, best_value = RecommendationEngine.identify_highlights(unique_flights)

        # 6. Recommendation presentation building. The branch lives in
        # `_build_recommendation` so it can be exercised without a provider, a
        # database or a model; its docstring records the defect it used to carry.
        rec = FlightSearchService._build_recommendation(cheapest, bool(unique_flights))

        # 7. Sorting
        unique_flights = RecommendationEngine.sort_flights(unique_flights, sorting)[:max_results]

        # 8. Fetch airports data for presentation
        airports_pres = []
        try:
            airports_data = self.repository.search_airports(origin_iata, 1) + self.repository.search_airports(destination_iata, 1)
            for a in airports_data:
                airports_pres.append(AirportPresentation(
                    iata=a.get("iata_code") or "",
                    city=a.get("city") or "",
                    name=a.get("name") or "",
                    country=a.get("country") or ""
                ))
        except Exception as e:
            logger.warning(f"Failed to fetch airports data: {e}")

        # Record metrics latency
        ObservabilityTracker.record_search_latency(time.time() - start_time, search_status)

        # A search that displayed flights from cache while persisting nothing, or
        # while the live provider was broken, is not a success. `count` (rows
        # displayed) and `rows_persisted` (rows the database confirmed) are now
        # separate numbers, and the caller can see which of the two it is reading.
        if search_status == "success" and (persistence_error or rows_persisted == -1):
            search_status = "degraded"

        return FlightSearchPresentation(
            cheapest=cheapest,
            fastest=fastest,
            best_value=best_value,
            recommendation=rec,
            flights=unique_flights,
            airports=airports_pres,
            metadata={
                "data_source": data_source,
                "count": len(unique_flights),
                "search_status": search_status,
                "search_id": search_id,
                "snapshot_id": snapshot_id,
                # Provenance, as reported by the transport rather than inferred.
                "provider_status": provider_status,
                "provider_error": provider_error,
                "provider_error_kind": provider_error_kind,
                "provider_attempts": provider_attempts,
                # Persistence, as confirmed by the database. rows_persisted is None
                # when no insert was attempted and -1 when it was attempted but
                # unconfirmed — neither of which may be read as "zero rows written".
                "rows_submitted": rows_submitted,
                "rows_persisted": rows_persisted,
                "persistence_error": persistence_error,
                # Not a persistence fault: these rows were collapsed before
                # submission because the provider listed one flight more than once,
                # so `rows_submitted` is already net of them.
                "provider_duplicate_rows": provider_duplicate_rows,
                # Also not a persistence fault, and also already netted out of
                # `rows_submitted`: observations refused at ingest. `currencies_seen`
                # is the diagnostic — a batch reading `{"USD": 20}` means Google
                # served the page in dollars and no FX rate is configured.
                "refused_rows": refused_rows,
                "refused_currencies": refused_currencies or None,
                # Of `rows_submitted`, how many were stored without a complete
                # booking-curve identity. Not a fault of the database and not netted
                # out of `rows_submitted` — these rows *are* written — but they can
                # never carry a supervised label, so a caller measuring whether a
                # collection run advanced the training corpus must subtract them.
                "unidentified_rows": unidentified_rows,
            }
        )

flight_search_service = FlightSearchService()

