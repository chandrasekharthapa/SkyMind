import pytest
import numpy as np
from datetime import datetime, timezone
from backend.ml.feature_context import FeatureContext
from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline

def test_feature_generation_determinism():
    ctx = FeatureContext(
        historical_data=[
            {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI", "price": 5000.0, "departure_date": "2026-07-26", "recorded_at": "2026-07-19T12:00:00Z"}
        ],
        market_snapshot={
            "lowest_fare": 5000.0, "highest_fare": 6000.0, "average_fare": 5500.0, "median_fare": 5500.0,
            "fare_spread": 1000.0, "price_std_dev": 100.0, "total_live_flights": 10,
            "direct_flight_count": 5, "connecting_flight_count": 5, "airline_distribution": {"AI": 5},
            "snapshot_quality": 1.0, "snapshot_completeness": 1.0
        },
        prediction_context={
            "origin": "DEL", "destination": "BOM", "airline": "AI", "departure_date": "2026-07-26",
            "current_price": 5200.0, "seats_available": 10, "days_until_dep": 7
        },
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
    )
    
    # Run the pipeline repeatedly 100 times using identical inputs
    hashes = set()
    first_features = None
    for _ in range(100):
        vec = feature_engineering_pipeline.build(ctx, "feature_set_v1")
        hashes.add(vec.feature_hash)
        if first_features is None:
            first_features = vec.features
        else:
            # Check identical feature values and ordering
            assert list(vec.features.keys()) == list(first_features.keys())
            for k in first_features.keys():
                val1 = first_features[k]
                val2 = vec.features[k]
                if isinstance(val1, float) and np.isnan(val1):
                    assert np.isnan(val2)
                else:
                    assert val1 == val2

    # Expect exactly 1 unique feature hash
    assert len(hashes) == 1
