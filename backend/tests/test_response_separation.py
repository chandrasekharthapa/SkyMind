import pytest
from backend.services.prediction_presentation import PredictionResponse

def test_response_observed_market_vs_forecast_separation():
    """Verify observed market data is strictly separated from forecasted timeline price data."""
    data = {
        "predicted_price": 5500.0,
        "current_market": {
            "lowest_fare": 5000.0,
            "average_fare": 7000.0,
            "snapshot_timestamp": "2026-07-20T12:00:00Z",
            "provider": "Google Flights"
        },
        "forecast": [
            {
                "day": 3,
                "date": "2026-07-23",
                "price": 5500.0,
                "lower": 5200.0,
                "upper": 5800.0,
                "forecast_price": 5500.0,
                "forecast_timestamp": "2026-07-23T12:00:00Z",
                "prediction_horizon": 3,
                "confidence": 75.0,
                "model_version": "2.0.0",
                "feature_schema_version": "2.0.0"
            }
        ],
        "recommendation": {
            "decision": "BOOK_NOW",
            "reasons": ["Forecast is higher than today's lowest fare"],
            "confidence": 75.0
        },
        "confidence": 75.0,
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
    # Today's observed market values are separated
    assert resp.current_market.lowest_fare == 5000.0
    assert resp.current_market.snapshot_timestamp == "2026-07-20T12:00:00Z"
    # Future forecasted outputs are separated
    assert resp.forecast[0].forecast_price == 5500.0
    assert resp.forecast[0].forecast_timestamp == "2026-07-23T12:00:00Z"
