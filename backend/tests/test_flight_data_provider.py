import pytest
import sys
import os
from unittest.mock import AsyncMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.flight_data_provider import GoogleFlightsProvider
from backend.services.flight_search_service import flight_search_service

@pytest.mark.asyncio
async def test_google_flights_provider_search(monkeypatch):
    """Verify GoogleFlightsProvider queries flight_search_service correctly."""
    mock_res = [{"flight_number": "6E101", "price": {"total": 5000.0, "currency": "INR"}}]
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(return_value=mock_res))

    provider = GoogleFlightsProvider()
    res = await provider.search("DEL", "BOM", "2026-07-26")

    assert res == mock_res
    assert provider.provider_name == "Google Flights MCP"


def test_only_implemented_providers_are_exported():
    """No provider class may exist whose `search` cannot return a fare.

    `AmadeusProvider`, `SabreProvider` and `CachedProvider` were each a single
    `return []` with no caller anywhere, and the test that covered two of them
    asserted that an empty list is an empty list. Together they presented four
    data sources with GDS failover where one scraper exists. This test fails if
    a placeholder is reintroduced under a vendor's name.
    """
    import backend.services.flight_data_provider as mod
    from backend.services.flight_data_provider import FlightDataProvider

    implementations = {
        name for name, obj in vars(mod).items()
        if isinstance(obj, type)
        and issubclass(obj, FlightDataProvider)
        and obj is not FlightDataProvider
    }
    assert implementations == {"GoogleFlightsProvider"}, implementations
