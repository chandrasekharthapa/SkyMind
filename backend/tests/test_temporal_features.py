import pytest
from datetime import datetime, timezone
from backend.ml.feature_context import FeatureContext
from backend.ml.features.temporal import TemporalGenerator

def test_temporal_features_inference():
    gen = TemporalGenerator()
    ctx = FeatureContext(
        historical_data=[],
        market_snapshot={},
        prediction_context={
            "departure_date": "2026-07-26",
            "departure_time": "2026-07-26T14:00:00"
        },
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
    )
    
    feats = gen.transform(ctx)
    assert feats["departure_day_of_week"] == 6  # Sunday
    assert feats["departure_month"] == 7
    assert feats["departure_quarter"] == 3
    assert feats["is_weekend"] is True
    assert feats["days_until_departure"] == 7
