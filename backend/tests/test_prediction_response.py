import pytest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.prediction_presentation import PredictionResponse, CurrentMarket, Recommendation, SearchMetadata, MarketSnapshotSummary

def test_prediction_response_validation():
    """Verify that PredictionResponse enforces strict Pydantic v2 schemas."""
    # Build complete dictionary matching the schema
    data = {
        "predicted_price": 5200.0,
        "current_market": {
            "lowest_fare": 5000.0,
            "average_fare": 7000.0,
            "snapshot_timestamp": "2026-07-20T12:00:00Z",
            "provider": "Google Flights"
        },
        "forecast": [
            {
                "day": 1,
                "date": "2026-07-27",
                "price": 5100.0,
                "lower": 4800.0,
                "upper": 5400.0,
                "forecast_price": 5100.0,
                "forecast_timestamp": "2026-07-27T12:00:00Z",
                "prediction_horizon": 1,
                "confidence": 70.0,
                "model_version": "1.0.0",
                "feature_schema_version": "1.0.0"
            }
        ],
        "recommendation": {
            "decision": "WAIT",
            "reasons": ["Price expected to stabilize"],
            "confidence": 85.0
        },
        "confidence": 85.0,
        "search_metadata": {
            "provider": "Google Flights",
            "retrieval_time": "2026-07-20T12:00:00Z",
            "search_latency": 0.35,
            "flight_count": 10,
            "market_freshness": 12.5,
            "cache_hit": True,
            "cache_miss": False,
            "refresh_reason": "TTL_EXPIRED",
            "snapshot_age": 12.5
        },
        "market_snapshot": {
            "total_live_flights": 10,
            "average_fare": 7000.0,
            "lowest_fare": 5000.0,
            "highest_fare": 9000.0,
            "connecting_flight_count": 8,
            "direct_flight_count": 2
        },
        "prediction_horizon": 3
    }
    
    resp = PredictionResponse(**data)
    assert resp.predicted_price == 5200.0
    assert resp.current_market.lowest_fare == 5000.0
    assert resp.recommendation.decision == "WAIT"
    assert resp.search_metadata.flight_count == 10
