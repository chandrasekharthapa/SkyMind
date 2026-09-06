"""SkyMind Flight Data Providers.

One interface, one implementation. The interface exists because
`MarketSnapshotProvider` takes a provider by injection and its tests substitute
failing and timing-out doubles for it; that is a real use, so the abstraction
stays.

Three further implementations used to live here — `AmadeusProvider`
("Amadeus GDS Sandbox"), `SabreProvider` ("Sabre GDS Sandbox") and
`CachedProvider` ("Supabase Cache Provider"). Each one's `search` was a single
`return []`. None was referenced by any production module: the only construction
site in the codebase is `market_snapshot_provider.py`, which defaults to
`GoogleFlightsProvider()`, so no request could ever reach them. What they
provided was a class list that reads as four data sources with GDS failover, and
an interviewer asking about the Amadeus integration would find one line
returning an empty list. They are deleted rather than implemented because there
are no Amadeus or Sabre credentials and no code anywhere that would consume a
second source; `MarketSnapshotProvider` calls exactly one provider and has no
failover logic to feed.

The Supabase cache is not lost with `CachedProvider`: reading cached snapshots is
`market_snapshot_provider.py`'s own job and it queries the database directly,
which is what that stub's comment ("handles direct DB queries") was pointing at.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from backend.services.flight_search_service import flight_search_service


class FlightDataProvider(ABC):
    """Abstract base provider for flight search interfaces."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider service."""

    @abstractmethod
    async def search(
        self,
        origin_iata: str,
        destination_iata: str,
        departure_date: str,
        cabin_class: str = "ECONOMY",
    ) -> List[Dict[str, Any]]:
        """Query raw normalized flight schedules/prices from the provider."""


class GoogleFlightsProvider(FlightDataProvider):
    """Live fares scraped from Google Flights, reached over the local MCP server.

    Both halves of the name are load-bearing. The transport is MCP
    (`services/mcp_client.py` spawns `india-flight-mcp/src/mcp/stdio_server.js`
    over stdio) and that server's one tool is backed by
    `providers/GoogleFlightsProvider.js`, which navigates
    `google.com/travel/flights`. This is the only provider: a MakeMyTrip scraper
    used to sit beside it in `backend/india-flight-mcp`, wired to nothing, and was
    deleted on 2026-09-03 once its failure had been measured (§42/§44 of
    AUDIT-FIXES.md). So there is no second source of a fare anywhere in the
    project — as the module docstring above says, nothing here has failover logic
    to feed, and a failed scrape is the end of the search.
    """

    @property
    def provider_name(self) -> str:
        return "Google Flights MCP"

    async def search(
        self,
        origin_iata: str,
        destination_iata: str,
        departure_date: str,
        cabin_class: str = "ECONOMY",
    ) -> List[Any]:
        res = await flight_search_service.search(
            origin_iata=origin_iata,
            destination_iata=destination_iata,
            departure_date=departure_date,
            adults=1,
            cabin_class=cabin_class,
            sorting="price",
        )
        if hasattr(res, "flights"):
            return res.flights
        if isinstance(res, list):
            return res
        return []
