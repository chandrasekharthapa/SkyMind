"""Flight Database Repository.

Provides decoupled methods for accessing Supabase price_history, flights,
and airport records.
"""

import logging
from typing import List, Dict, Any, Optional, Protocol
from backend.database.database import database as db

logger = logging.getLogger(__name__)

class FlightRepositoryInterface(Protocol):
    def get_price_history_cache(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        max_results: int,
        *,
        airline_code: Optional[str] = None,
        flight_number: Optional[str] = None,
    ) -> List[Dict[str, Any]]: ...
    def search_airports(self, query: str, limit: int = 10) -> List[Dict[str, Any]]: ...

class SupabaseFlightRepository(FlightRepositoryInterface):
    def get_price_history_cache(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        max_results: int,
        *,
        airline_code: Optional[str] = None,
        flight_number: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch recorded price observations for a route, newest first.

        `airline_code` and `flight_number` narrow the result toward a single
        booking curve. They are keyword-only and default to None, so the existing
        positional callers — the search cache in `flight_search_service` and the
        route-level trend answer in `chatbot_tools`, both of which genuinely want
        every carrier — are unchanged.

        They exist because `max_results` is applied by the database, after the
        filters and before any narrowing the caller does in Python. The prediction
        and forecast paths compute booking-curve features for one flight, and
        `price_changes_from_records` narrows to that flight *after* this query has
        already discarded rows: on a route with several carriers a day, the newest
        100 route-wide rows can contain nought to two observations of the flight
        being quoted, so the movement features came out NaN and the resulting
        refusal reported the route's observation count as the reason. Filtering
        here means the cap bounds the curve the features are about.

        Both filters are optional on purpose rather than required: a live snapshot
        may name a carrier without a flight number, and the query should then be as
        narrow as the identity actually known and no narrower.

        A query failure still returns `[]`, because five callers treat this as a
        cache and an outage must not take the search path down with it — but it is
        now logged. Callers cannot tell "no observations recorded" from "the
        database did not answer", so a refusal downstream that names an observation
        count is only accurate when nothing was logged here.
        """
        try:
            query = db.supabase.table("price_history") \
                .select("*") \
                .eq("origin_code", origin) \
                .eq("destination_code", destination) \
                .eq("departure_date", departure_date)
            if airline_code:
                query = query.eq("airline_code", airline_code)
            if flight_number:
                query = query.eq("flight_number", flight_number)
            res = query \
                .order("recorded_at", desc=True) \
                .limit(max_results) \
                .execute()
            return res.data or []
        except Exception:
            logger.exception(
                "price_history query failed for %s-%s on %s (airline=%s, flight=%s); "
                "returning no rows, which downstream cannot distinguish from an "
                "empty history.",
                origin, destination, departure_date, airline_code, flight_number,
            )
            return []

    def search_airports(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search airports table by city, IATA code, or name."""
        try:
            res = db.supabase.table("airports").select("iata_code, name, city, country") \
                .or_(f"iata_code.ilike.%{query}%,city.ilike.%{query}%,name.ilike.%{query}%") \
                .limit(limit) \
                .execute()
            return res.data or []
        except Exception:
            return []

flight_repository = SupabaseFlightRepository()
