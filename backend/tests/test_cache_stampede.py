import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from backend.services.market_snapshot_provider import MarketSnapshotProvider

@pytest.mark.asyncio
async def test_cache_stampede_prevention():
    """Verify that multiple concurrent queries for the same key share a single live search call."""
    mock_provider = MagicMock()
    mock_provider.provider_name = "Google Flights MCP"
    
    # Mock search to delay 0.1 seconds
    async def slow_search(*args, **kwargs):
        await asyncio.sleep(0.1)
        return [
            {
                "price": {"total": 5000.0},
                "itineraries": [{"segments": [{"departure_time": "2026-07-26T08:00:00"}]}],
                "primary_airline": "AI"
            }
        ]
    mock_provider.search = AsyncMock(side_effect=slow_search)
    
    provider_service = MarketSnapshotProvider(provider=mock_provider)
    
    # Trigger 5 concurrent calls
    tasks = [
        provider_service.get_market_snapshot("DEL", "BOM", "2026-07-26")
        for _ in range(5)
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Verify we got 5 results
    assert len(results) == 5
    for r in results:
        assert r.lowest_fare == 5000.0
        
    # Crucial assertion: provider.search must have been called EXACTLY ONCE
    assert mock_provider.search.call_count == 1
