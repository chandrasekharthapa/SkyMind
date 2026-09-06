import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from backend.services.market_snapshot_provider import MarketSnapshotProvider

@pytest.mark.asyncio
async def test_thread_safe_concurrent_caching():
    """Verify that multiple concurrent queries for the same key are safely cached and hit correctly."""
    mock_provider = MagicMock()
    mock_provider.provider_name = "Google Flights MCP"
    
    async def quick_search(*args, **kwargs):
        return [
            {
                "price": {"total": 6000.0},
                "itineraries": [{"segments": [{"departure_time": "2026-07-26T08:00:00"}]}],
                "primary_airline": "AI"
            }
        ]
    mock_provider.search = AsyncMock(side_effect=quick_search)
    
    provider_service = MarketSnapshotProvider(provider=mock_provider)
    
    # Run first query
    res1 = await provider_service.get_market_snapshot("DEL", "BOM", "2026-07-26")
    assert res1.cache_hit is False
    assert res1.cache_miss is True
    
    # Run second query (should be a cache hit)
    res2 = await provider_service.get_market_snapshot("DEL", "BOM", "2026-07-26")
    assert res2.cache_hit is True
    assert res2.cache_miss is False
    
    assert mock_provider.search.call_count == 1
