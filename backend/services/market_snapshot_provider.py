"""Market Snapshot Provider.

Maintains an in-memory thread-safe cache for live market data snapshots,
abstracting flight searches, calculating statistical metrics, and respecting TTL.
Implements circuit breaker, retries, stale fallbacks, cache stampede prevention,
and OpenTelemetry metric tracking.
"""

import time
import math
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import numpy as np

from opentelemetry import metrics

from backend.domain.market_snapshot import MarketSnapshot
from backend.domain.domain_events import DomainEvent, event_dispatcher
from backend.services.flight_data_provider import FlightDataProvider, GoogleFlightsProvider
from backend.services.booking_curve_definition import MIN_OBSERVATIONS_FOR_STD
from backend.services.market_aggregate_definition import (
    STD_DDOF,
    snapshot_completeness_score,
    snapshot_quality_score,
)
from backend.utils.resilience import CircuitBreaker
from backend.services.event_publisher import EventPublisher, AuditLogEventPublisher

logger = logging.getLogger(__name__)

# Cache configuration
MARKET_SNAPSHOT_TTL = 300
MAX_STALE_SNAPSHOT_AGE = 86400  # 24 hours
REQUEST_TIMEOUT = 30.0

# OpenTelemetry observability counters and gauges
meter = metrics.get_meter("skymind.market_snapshot")

cache_hits_counter = meter.create_counter(
    name="market_snapshot_cache_hits_total",
    description="Total cache hits for market snapshots"
)
cache_misses_counter = meter.create_counter(
    name="market_snapshot_cache_misses_total",
    description="Total cache misses for market snapshots"
)
search_latency_hist = meter.create_histogram(
    name="market_search_latency_seconds",
    description="Upstream flight search latency"
)
snapshot_latency_hist = meter.create_histogram(
    name="market_snapshot_generation_seconds",
    description="Time taken to calculate snapshot aggregates"
)
snapshot_age_gauge = meter.create_gauge(
    name="market_snapshot_age_seconds",
    description="Age in seconds of retrieved market snapshots"
)

class MarketSnapshotProvider:
    def __init__(self, provider: Optional[FlightDataProvider] = None, event_publisher: Optional[EventPublisher] = None):
        # Cache stores: (timestamp, MarketSnapshot)
        self._cache: Dict[str, tuple[float, MarketSnapshot]] = {}
        # Stampede prevention: tracks key -> Task[MarketSnapshot]
        self._pending_tasks: Dict[str, asyncio.Task[MarketSnapshot]] = {}
        # Dependency Injection of flight data provider (defaults to Google Flights MCP)
        self.provider = provider or GoogleFlightsProvider()
        # Internal Circuit Breaker for snapshot queries
        self._breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
        self.event_publisher = event_publisher or AuditLogEventPublisher()

    def _get_cache_key(self, origin: str, destination: str, departure_date: str) -> str:
        return f"{origin.upper()}-{destination.upper()}-{departure_date}"

    async def get_market_snapshot(
        self, origin: str, destination: str, departure_date: str, manual_refresh: bool = False
    ) -> MarketSnapshot:
        """Fetch the freshest market snapshot, utilizing thread-safe cache if within TTL."""
        cache_key = self._get_cache_key(origin, destination, departure_date)
        now = time.time()
        
        # Check cache hit (only when not manual refresh)
        if cache_key in self._cache and not manual_refresh:
            cached_time, snapshot = self._cache[cache_key]
            age = now - cached_time
            if age < MARKET_SNAPSHOT_TTL:
                cache_hits_counter.add(1, {"cache_hit": "true"})
                snapshot_age_gauge.set(age)
                logger.info(f"MarketSnapshot Cache Hit for {cache_key} (Age: {age:.1f}s)")
                
                updated_snapshot = snapshot.copy(update={
                    "cache_hit": True,
                    "cache_miss": False,
                    "snapshot_age": age,
                    "refresh_reason": "TTL_EXPIRED"
                })
                self.event_publisher.publish("SnapshotCreated", {
                    "origin": origin,
                    "destination": destination,
                    "provider": updated_snapshot.provider,
                    "quality": updated_snapshot.snapshot_quality,
                    "cache_hit": True
                })
                return updated_snapshot

        # Cache Stampede Prevention: if refresh task is already active, await it!
        if cache_key in self._pending_tasks:
            logger.info(f"[STAMPEDE PREVENTION] Awaiting active refresh task for key: {cache_key}")
            return await self._pending_tasks[cache_key]

        # Execute refresh flow as a task to share execution among concurrent requests
        refresh_task = asyncio.create_task(
            self._execute_refresh_flow(origin, destination, departure_date, manual_refresh)
        )
        self._pending_tasks[cache_key] = refresh_task
        try:
            return await refresh_task
        finally:
            self._pending_tasks.pop(cache_key, None)

    async def _execute_refresh_flow(
        self, origin: str, destination: str, departure_date: str, manual_refresh: bool
    ) -> MarketSnapshot:
        cache_key = self._get_cache_key(origin, destination, departure_date)
        now = time.time()
        
        # Cache Miss or Manual Refresh or Expired TTL
        cache_misses_counter.add(1, {"cache_miss": "true"})
        
        # Determine refresh reason
        if manual_refresh:
            reason = "MANUAL_REFRESH"
        elif cache_key not in self._cache:
            reason = "STARTUP" if not self._cache else "TTL_EXPIRED"
        else:
            reason = "TTL_EXPIRED"
            
        logger.info(f"MarketSnapshot Cache Miss ({reason}) for {cache_key}. Triggering live refresh.")
        
        event_dispatcher.dispatch(DomainEvent(
            event_type="ProviderRefreshTriggered",
            metadata={"reason": reason, "key": cache_key}
        ))
        
        # Search live with retries, timeout, and circuit breaker
        start_search = time.time()
        flights = []
        search_success = True
        provider_name = self.provider.provider_name
        
        # Verify circuit breaker state
        if not self._breaker.allow_request():
            logger.error(f"Circuit Breaker for MarketSnapshotProvider is OPEN. Skipping live query.")
            search_success = False
        else:
            try:
                # Execution with timeout and exponential backoff retries
                flights = await self._search_with_retry_and_timeout(
                    origin, destination, departure_date
                )
                self._breaker.record_success()
            except Exception as e:
                self._breaker.record_failure()
                logger.error(f"Live provider search failed in snapshot provider: {e}")
                search_success = False

        search_dur = time.time() - start_search
        search_latency_hist.record(search_dur)
        
        # If search failed, attempt failover to stale cache falls back
        if not search_success:
            if cache_key in self._cache:
                cached_time, snapshot = self._cache[cache_key]
                stale_age = now - cached_time
                if stale_age < MAX_STALE_SNAPSHOT_AGE:
                    logger.warning(
                        f"Live search failed. Falling back to stale snapshot for {cache_key} (Age: {stale_age:.1f}s)"
                    )
                    # Mark snapshot quality as stale
                    stale_snapshot = MarketSnapshot(
                        lowest_fare=snapshot.lowest_fare,
                        highest_fare=snapshot.highest_fare,
                        average_fare=snapshot.average_fare,
                        median_fare=snapshot.median_fare,
                        fare_spread=snapshot.fare_spread,
                        price_std_dev=snapshot.price_std_dev,
                        total_live_flights=snapshot.total_live_flights,
                        direct_flight_count=snapshot.direct_flight_count,
                        connecting_flight_count=snapshot.connecting_flight_count,
                        # Copied field by field, so the identity has to be copied
                        # too: a stale snapshot that kept `lowest_fare` and dropped
                        # whose fare it is would put the serving path back where it
                        # started, on the degraded path only.
                        cheapest_airline=snapshot.cheapest_airline,
                        cheapest_flight_number=snapshot.cheapest_flight_number,
                        cheapest_seats_available=snapshot.cheapest_seats_available,
                        cheapest_departure_time=snapshot.cheapest_departure_time,
                        cheapest_by_airline=snapshot.cheapest_by_airline,
                        airline_distribution=snapshot.airline_distribution,
                        departure_distribution=snapshot.departure_distribution,
                        seat_information=snapshot.seat_information,
                        retrieval_timestamp=snapshot.retrieval_timestamp,
                        provider=snapshot.provider,
                        search_duration=snapshot.search_duration,
                        search_success=False,
                        snapshot_quality=0.5,  # Stale degrades quality to half
                        snapshot_completeness=snapshot.snapshot_completeness,
                        missing_fields=snapshot.missing_fields + ["stale_fallback"],
                        provider_status="DEGRADED",
                        cache_hit=True,
                        cache_miss=False,
                        snapshot_age=stale_age,
                        refresh_reason="TTL_EXPIRED"
                    )
                    self.event_publisher.publish("SnapshotCreated", {
                        "origin": origin,
                        "destination": destination,
                        "provider": stale_snapshot.provider,
                        "quality": stale_snapshot.snapshot_quality,
                        "cache_hit": True,
                        "stale": True
                    })
                    # Re-cache stale snapshot with current time to throttle repeated failed hits
                    self._cache[cache_key] = (now, stale_snapshot)
                    return stale_snapshot

        # Build snapshot from search results
        snapshot_start = time.time()
        snapshot = self._build_snapshot(
            flights=flights,
            provider=provider_name,
            search_duration=search_dur,
            search_success=search_success
        )
        snapshot_latency_hist.record(time.time() - snapshot_start)
        
        # Cache snapshot with metadata populated
        snapshot_updated = snapshot.copy(update={
            "cache_hit": False,
            "cache_miss": True,
            "snapshot_age": 0.0,
            "refresh_reason": reason
        })
        self._cache[cache_key] = (time.time(), snapshot_updated)
        
        self.event_publisher.publish("SnapshotCreated", {
            "origin": origin,
            "destination": destination,
            "provider": snapshot_updated.provider,
            "quality": snapshot_updated.snapshot_quality,
            "cache_hit": False
        })
        
        event_dispatcher.dispatch(DomainEvent(
            event_type="MarketSnapshotCreated",
            metadata={
                "key": cache_key,
                "quality": snapshot.snapshot_quality,
                "completeness": snapshot.snapshot_completeness,
                "success": search_success
            }
        ))
        
        return snapshot_updated

    async def _search_with_retry_and_timeout(
        self, origin: str, destination: str, departure_date: str
    ) -> List[Dict[str, Any]]:
        """Executes the query with a strict timeout and exponential backoff retry policy."""
        retries = 3
        delay = 0.5
        for attempt in range(retries):
            try:
                # Enforce timeout
                return await asyncio.wait_for(
                    self.provider.search(
                        origin_iata=origin,
                        destination_iata=destination,
                        departure_date=departure_date,
                        cabin_class="ECONOMY"
                    ),
                    timeout=REQUEST_TIMEOUT
                )
            except (asyncio.TimeoutError, Exception) as err:
                if attempt == retries - 1:
                    raise err
                logger.warning(
                    f"Search attempt {attempt + 1} failed with error: {err}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
                delay *= 2.0
        return []

    def _build_snapshot(
        self, flights: List[Any], provider: str, search_duration: float, search_success: bool
    ) -> MarketSnapshot:
        """Parses canonical NormalizedFlight objects, aggregates statistical indicators, and calculates quality indices."""
        retrieval_timestamp = datetime.now(timezone.utc).isoformat()
        
        if not flights or not search_success:
            return MarketSnapshot(
                lowest_fare=np.nan,
                highest_fare=np.nan,
                average_fare=np.nan,
                median_fare=np.nan,
                fare_spread=np.nan,
                price_std_dev=np.nan,
                total_live_flights=0,
                direct_flight_count=0,
                connecting_flight_count=0,
                # No flights, so no cheapest one. Stated rather than left to the
                # model default, so that both return sites name the field and a
                # later change to the default cannot quietly give this branch an
                # identity it does not have.
                cheapest_airline=None,
                cheapest_flight_number=None,
                cheapest_seats_available=None,
                cheapest_departure_time=None,
                cheapest_by_airline={},
                airline_distribution={},
                departure_distribution={"morning": 0, "afternoon": 0, "evening": 0},
                seat_information=None,
                retrieval_timestamp=retrieval_timestamp,
                provider=provider,
                search_duration=search_duration,
                search_success=search_success,
                snapshot_quality=0.0,
                snapshot_completeness=0.0,
                missing_fields=["flights_data"],
                provider_status="OFFLINE" if not search_success else "ONLINE"
            )
            
        prices: List[float] = []
        direct_count = 0
        connecting_count = 0
        unknown_stops_count = 0
        airlines: Dict[str, int] = {}
        departure_dist = {"morning": 0, "afternoon": 0, "evening": 0}
        seats_list: List[int] = []
        # The flight `lowest_fare` belongs to. `prices` is flattened and sorted
        # below, which discards it, and two consumers then guessed: the airline
        # from the first key of `airline_distribution` and the flight number not at
        # all. Carried as (fare, airline, number) so the comparison is on the same
        # figure that becomes `lowest_fare`.
        cheapest: Optional[tuple] = None
        # And the same per carrier, as (fare, number, seats, departure_time), for a
        # caller who names the airline they are asking about: the market minimum is
        # not that airline's price.
        cheapest_by_airline: Dict[str, tuple] = {}

        for f in flights:
            # Safely extract price whether f is a NormalizedFlight model or dictionary
            price_val = getattr(f, "price", None)
            if price_val is None and isinstance(f, dict):
                p = f.get("price")
                if isinstance(p, dict):
                    price_val = p.get("total")
                else:
                    price_val = p

            price_float: Optional[float] = None
            if price_val is not None:
                try:
                    parsed = float(price_val)
                    if parsed > 0:
                        price_float = parsed
                        prices.append(parsed)
                except (ValueError, TypeError):
                    pass

            # Segments/Stops & Departure Distribution
            itins = getattr(f, "itineraries", None) or (f.get("itineraries") if isinstance(f, dict) else [])
            # None, not 0: a flight with no segment data has an unknown stop count.
            # This defaulted to 0, so every flight the provider could not read was
            # counted as a non-stop and inflated `direct_flight_count`.
            stops = None
            # Bound before the branches below, because it is now read after them: it
            # is this flight's own departure time, and it is carried through to the
            # snapshot for the one flight the prediction is about rather than only
            # counted into a three-bucket histogram. Unbound-if-absent would have
            # made a missing itinerary a NameError at the cheapest-flight comparison.
            dep_time_str = None
            if itins:
                first_itin = itins[0]
                segs = getattr(first_itin, "segments", None) or (first_itin.get("segments") if isinstance(first_itin, dict) else [])
                if segs:
                    stops = len(segs) - 1
                    first_seg = segs[0]
                    dep_time_str = getattr(first_seg, "departure_time", None) or (first_seg.get("departure_time") if isinstance(first_seg, dict) else None)
                    if dep_time_str:
                        try:
                            if "T" in str(dep_time_str):
                                hour_part = str(dep_time_str).split("T")[1]
                                hour = int(hour_part.split(":")[0])
                            else:
                                dt = datetime.fromisoformat(str(dep_time_str))
                                hour = dt.hour
                            if 5 <= hour < 12:
                                departure_dist["morning"] += 1
                            elif 12 <= hour < 18:
                                departure_dist["afternoon"] += 1
                            else:
                                departure_dist["evening"] += 1
                        except Exception:
                            pass

            if stops is None:
                unknown_stops_count += 1
            elif stops == 0:
                direct_count += 1
            else:
                connecting_count += 1

            # Airline code
            airline = getattr(f, "primary_airline", None) or (f.get("primary_airline") if isinstance(f, dict) else None)
            if airline:
                airlines[airline] = airlines.get(airline, 0) + 1

            # Seats information. Read before the cheapest-flight comparisons below,
            # which now carry it: `seats_available` is a per-flight column in
            # `price_history`, so the model was fitted on one flight's seat count,
            # and the consumer had nothing per-flight to send it.
            seats = getattr(f, "seats_available", None) or (f.get("seats_available") if isinstance(f, dict) else None)
            seats_int: Optional[int] = None
            if seats is not None:
                try:
                    seats_int = int(seats)
                except (ValueError, TypeError):
                    seats_int = None
            if seats_int is not None:
                seats_list.append(seats_int)

            # Whose fare the eventual `lowest_fare` is. Read here rather than after
            # the loop because `prices` keeps no provenance, and read from the same
            # top-level `flight_number` the ingest path writes to `price_history`
            # (`flight_search_service` line 165) — a snapshot naming the flight by a
            # different string than the stored observations would match no curve,
            # which is the state this field exists to end. Strictly less-than, so a
            # tie keeps the first flight the provider listed and the field is a
            # function of the response rather than of iteration luck.
            #
            # `seats_int` and `dep_time_str` ride along for the same reason the
            # number does: they are properties of this one flight, and the aggregates
            # computed below cannot be taken apart into them afterwards.
            if price_float is not None and (cheapest is None or price_float < cheapest[0]):
                number = getattr(f, "flight_number", None) or (
                    f.get("flight_number") if isinstance(f, dict) else None)
                cheapest = (price_float, airline, number, seats_int, dep_time_str)

            if price_float is not None and airline:
                prior = cheapest_by_airline.get(airline)
                if prior is None or price_float < prior[0]:
                    number = getattr(f, "flight_number", None) or (
                        f.get("flight_number") if isinstance(f, dict) else None)
                    cheapest_by_airline[airline] = (
                        price_float, number, seats_int, dep_time_str)

        # Calculate statistics
        prices = sorted(prices)
        total_live_flights = len(flights)
        
        if prices:
            lowest_fare = float(prices[0])
            highest_fare = float(prices[-1])
            average_fare = float(np.mean(prices))
            median_fare = float(np.median(prices))
            fare_spread = float(highest_fare - lowest_fare)
            # Sample std (ddof=1), and NaN — not 0.0 — below two observations.
            # This was `np.std(prices)`, the population std, while the training
            # path used pandas' ddof=1 under the same feature name; and a single
            # fare reported dispersion 0.0, which is a claim, not a measurement.
            # `STD_DDOF` and `MIN_OBSERVATIONS_FOR_STD` are shared with
            # `market_aggregate_definition`, which is what the model trains on.
            price_std_dev = (
                float(np.std(prices, ddof=STD_DDOF))
                if len(prices) >= MIN_OBSERVATIONS_FOR_STD else float("nan")
            )
        else:
            lowest_fare = np.nan
            highest_fare = np.nan
            average_fare = np.nan
            median_fare = np.nan
            fare_spread = np.nan
            price_std_dev = np.nan

        # Seat Statistics
        seat_information = None
        if seats_list:
            seat_information = {
                "minimum": int(np.min(seats_list)),
                "maximum": int(np.max(seats_list)),
                "average": float(np.mean(seats_list)),
                "min": int(np.min(seats_list)),
                "max": int(np.max(seats_list)),
                "avg": float(np.mean(seats_list))
            }

        # Quality Metrics calculations — one definition, shared with the training
        # path. These used to be computed here and hardcoded to 1.0 for every
        # training row, so the model never saw the feature vary before production
        # showed it a discounted score.
        complete_fares = len(prices)
        completeness = snapshot_completeness_score(total_live_flights, complete_fares)
        quality = snapshot_quality_score(total_live_flights, complete_fares,
                                         search_success=search_success)
        if np.isnan(completeness):
            completeness = 0.0
        if np.isnan(quality):
            quality = 0.0

        # Missing attributes compilation
        missing = []
        if not prices:
            missing.append("flight_fares")
        if not seats_list:
            missing.append("seats_data")
        if unknown_stops_count:
            # These flights are in neither `direct_flight_count` nor
            # `connecting_flight_count`, so say so rather than let the two counts
            # silently fail to sum to `total_live_flights`.
            missing.append(f"stop_counts:{unknown_stops_count}")
        if prices and cheapest is not None and not cheapest[2]:
            # The cheapest flight is priced but unnamed, so it is on no booking
            # curve and the consumer will get NaN curve features for it. Recorded
            # because that is a property of the provider's response, not of the
            # consumer, and it is the one field whose absence quietly costs
            # fourteen features.
            missing.append("cheapest_flight_number")

        return MarketSnapshot(
            lowest_fare=lowest_fare,
            highest_fare=highest_fare,
            average_fare=average_fare,
            median_fare=median_fare,
            fare_spread=fare_spread,
            price_std_dev=price_std_dev,
            total_live_flights=total_live_flights,
            direct_flight_count=direct_count,
            connecting_flight_count=connecting_count,
            cheapest_airline=cheapest[1] if cheapest else None,
            cheapest_flight_number=cheapest[2] if cheapest else None,
            cheapest_seats_available=cheapest[3] if cheapest else None,
            cheapest_departure_time=cheapest[4] if cheapest else None,
            cheapest_by_airline={
                code: {"fare": fare, "flight_number": number,
                       "seats_available": seats, "departure_time": dep_time}
                for code, (fare, number, seats, dep_time) in cheapest_by_airline.items()
            },
            airline_distribution=airlines,
            departure_distribution=departure_dist,
            seat_information=seat_information,
            retrieval_timestamp=retrieval_timestamp,
            provider=provider,
            search_duration=search_duration,
            search_success=search_success,
            snapshot_quality=round(quality, 2),
            snapshot_completeness=round(completeness, 2),
            missing_fields=missing,
            provider_status="ONLINE"
        )

# Singleton provider instance
market_snapshot_provider = MarketSnapshotProvider()
