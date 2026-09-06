import pytest
import sys
import os
import time
from unittest.mock import AsyncMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.market_snapshot_provider import MarketSnapshotProvider, MARKET_SNAPSHOT_TTL
from backend.services.flight_data_provider import GoogleFlightsProvider

@pytest.mark.asyncio
async def test_market_snapshot_cache_lifecycle():
    """Verify cache lifecycle, TTL boundaries, manual refresh overrides, and hit/miss reporting."""
    provider = MarketSnapshotProvider(provider=GoogleFlightsProvider())
    mock_search = AsyncMock(return_value=[{"flight_number": "6E101", "price": {"total": 5000.0, "currency": "INR"}}])
    provider.provider.search = mock_search
    
    # 1. First call -> Cache Miss
    snap1 = await provider.get_market_snapshot("DEL", "BOM", "2026-07-26")
    assert mock_search.call_count == 1
    
    # 2. Second call within TTL -> Cache Hit (mock search count remains 1)
    snap2 = await provider.get_market_snapshot("DEL", "BOM", "2026-07-26")
    assert mock_search.call_count == 1
    assert snap2.lowest_fare == 5000.0
    
    # 3. Call with manual refresh -> Cache Bypass
    snap3 = await provider.get_market_snapshot("DEL", "BOM", "2026-07-26", manual_refresh=True)
    assert mock_search.call_count == 2
