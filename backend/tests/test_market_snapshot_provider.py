import pytest
import sys
import os
import asyncio
from unittest.mock import AsyncMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.market_snapshot_provider import MarketSnapshotProvider
from backend.services.flight_data_provider import FlightDataProvider, GoogleFlightsProvider

class MockFailedDataProvider(FlightDataProvider):
    @property
    def provider_name(self) -> str:
        return "Mock Fail Provider"
    async def search(self, origin, destination, departure_date, cabin_class="ECONOMY"):
        raise RuntimeError("Search API failure")

class MockTimeoutDataProvider(FlightDataProvider):
    @property
    def provider_name(self) -> str:
        return "Mock Timeout Provider"
    async def search(self, origin, destination, departure_date, cabin_class="ECONOMY"):
        await asyncio.sleep(6.0)  # Exceeds the 5s timeout limit
        return []

@pytest.mark.asyncio
async def test_snapshot_provider_exponential_retry_and_timeout():
    """Verify market snapshot provider timeout logic."""
    provider = MarketSnapshotProvider(provider=MockTimeoutDataProvider())
    # Should catch TimeoutError, record fail, and return empty snapshot
    snapshot = await provider.get_market_snapshot("DEL", "BOM", "2026-07-26")
    assert snapshot.search_success is False
    assert snapshot.snapshot_quality == 0.0

@pytest.mark.asyncio
async def test_snapshot_provider_stale_cache_fallback():
    """Verify failover falls back to stale cache within MAX_STALE_SNAPSHOT_AGE."""
    # Create provider with custom caching populated
    provider = MarketSnapshotProvider(provider=GoogleFlightsProvider())
    mock_flights = [{"flight_number": "6E101", "price": {"total": 5000.0, "currency": "INR"}}]
    
    # 1. Populate cache with a valid snapshot
    provider.provider = AsyncMock()
    provider.provider.provider_name = "Mock Provider"
    provider.provider.search = AsyncMock(return_value=mock_flights)
    
    snapshot_1 = await provider.get_market_snapshot("DEL", "BOM", "2026-07-26")
    assert snapshot_1.search_success is True
    
    # 2. Swap to failing provider to simulate upstream failure
    provider.provider = MockFailedDataProvider()
    snapshot_2 = await provider.get_market_snapshot("DEL", "BOM", "2026-07-26", manual_refresh=True)
    
    # Assert stale cache is returned with warning quality
    assert snapshot_2.lowest_fare == 5000.0
    assert snapshot_2.snapshot_quality == 0.5
    assert "stale_fallback" in snapshot_2.missing_fields
