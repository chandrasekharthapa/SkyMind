import pytest
from unittest.mock import MagicMock, AsyncMock
from backend.services.market_snapshot_provider import MarketSnapshotProvider
from backend.domain.market_snapshot import MarketSnapshot

@pytest.mark.asyncio
async def test_provider_failover_to_stale_cache():
    """Verify fallback to stale cache upon provider outage."""
    mock_provider = MagicMock()
    # Live search fails
    mock_provider.search = AsyncMock(side_effect=Exception("API Outage"))
    mock_provider.provider_name = "Google Flights MCP"
    
    provider_service = MarketSnapshotProvider(provider=mock_provider)
    
    # Pre-populate cache with a valid snapshot
    cached_snapshot = MarketSnapshot(
        lowest_fare=5000.0,
        highest_fare=10000.0,
        average_fare=7500.0,
        median_fare=7500.0,
        fare_spread=5000.0,
        price_std_dev=2500.0,
        total_live_flights=2,
        direct_flight_count=2,
        connecting_flight_count=0,
        retrieval_timestamp="2026-07-20T12:00:00Z",
        provider="Google Flights MCP",
        search_success=True
    )
    import time
    provider_service._cache["DEL-BOM-2026-07-26"] = (time.time() - 600, cached_snapshot) # expired TTL but within stale age
    
    # Requesting snapshot during outage should failover to stale cache
    result = await provider_service.get_market_snapshot("DEL", "BOM", "2026-07-26")
    
    assert result.search_success is False
    assert result.snapshot_quality == 0.5
    assert result.provider_status == "DEGRADED"
    assert result.cache_hit is True
