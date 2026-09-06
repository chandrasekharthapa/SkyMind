import pytest
from backend.domain.market_snapshot import MarketSnapshot

def test_market_snapshot_context_fields():
    """Verify MarketSnapshot fields and cache metadata attributes are present."""
    snapshot = MarketSnapshot(
        lowest_fare=5000.0,
        highest_fare=10000.0,
        average_fare=7500.0,
        median_fare=7500.0,
        fare_spread=5000.0,
        price_std_dev=2500.0,
        total_live_flights=10,
        direct_flight_count=2,
        connecting_flight_count=8,
        retrieval_timestamp="2026-07-20T12:00:00Z",
        provider="Google Flights",
        search_duration=0.5,
        search_success=True,
        snapshot_quality=0.95,
        snapshot_completeness=1.0,
        provider_status="ONLINE",
        snapshot_age=30.0,
        cache_hit=True,
        cache_miss=False,
        refresh_reason="TTL_EXPIRED"
    )
    
    assert snapshot.lowest_fare == 5000.0
    assert snapshot.highest_fare == 10000.0
    assert snapshot.snapshot_quality == 0.95
    assert snapshot.snapshot_age == 30.0
    assert snapshot.cache_hit is True
    assert snapshot.cache_miss is False
    assert snapshot.refresh_reason == "TTL_EXPIRED"
