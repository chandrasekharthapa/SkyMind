import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from backend.ml.feature_context import FeatureContext
from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline

def test_pipeline_inference_and_training():
    ctx = FeatureContext(
        historical_data=[
            {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI", "price": 5000.0, "departure_date": "2026-07-26", "recorded_at": "2026-07-19T12:00:00Z"},
            {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI", "price": 5500.0, "departure_date": "2026-07-26", "recorded_at": "2026-07-20T12:00:00Z"}
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
    
    # 1. Build legacy vector
    vec_legacy = feature_engineering_pipeline.build(ctx, "legacy")
    assert len(vec_legacy.features) == 16
    assert vec_legacy.features["origin_code"] == "DEL"
    assert vec_legacy.features["destination_code"] == "BOM"
    
    # 2. Build V1 vector
    vec_v1 = feature_engineering_pipeline.build(ctx, "feature_set_v1")
    assert len(vec_v1.features) > 16
    assert "rolling_mean_price" in vec_v1.features
