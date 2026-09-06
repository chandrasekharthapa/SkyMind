import pytest
from datetime import datetime, timezone
from backend.ml.feature_context import FeatureContext
from backend.ml.features.market import MarketGenerator

def test_market_features_inference():
    gen = MarketGenerator()
    ctx = FeatureContext(
        historical_data=[],
        market_snapshot={
            "lowest_fare": 5000.0, "highest_fare": 6000.0, "average_fare": 5500.0, "median_fare": 5500.0,
            "fare_spread": 1000.0, "price_std_dev": 100.0, "total_live_flights": 10,
            "direct_flight_count": 5, "connecting_flight_count": 5, "airline_distribution": {"AI": 5},
            "snapshot_quality": 1.0, "snapshot_completeness": 1.0
        },
        prediction_context={},
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
    )
    
    feats = gen.transform(ctx)
    assert feats["lowest_fare"] == 5000.0
    assert feats["fare_spread"] == 1000.0
    assert feats["total_live_flights"] == 10
    assert feats["direct_ratio"] == 0.5
    assert feats["connecting_ratio"] == 0.5
