import pytest
import sys
import os
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.prediction_service import PredictionService
from backend.services.flight_search_service import flight_search_service
from backend.ml.price_model import get_predictor
from backend.tests.model_availability import requires_trained_model

# Dynamic future date so this test never fails due to date drift
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
FUTURE_DATETIME = f"{FUTURE_DATE}T14:00:00"
D1 = (date.today() + timedelta(days=31)).strftime("%Y-%m-%d")

@pytest.mark.asyncio
async def test_prediction_response_separation_fields(monkeypatch):
    """Verify prediction response schema clearly separates observed live fares and model forecasts.

    Gated even though it is a shape test: patching `forecast` and `predict` does not
    get past `PredictionService.predict`'s capability precondition, which reads the
    registry rather than the predictor, so with the shipped artifacts quarantined
    there is no response whose shape could be inspected.
    """
    requires_trained_model()

    mock_flights = [
        {"flight_number": "AI101", "price": {"total": 5000.0, "currency": "INR"}, "primary_airline": "AI", "itineraries": [{"segments": [{"departure_time": FUTURE_DATETIME}]}], "seats_available": 15}
    ]
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(return_value=mock_flights))
    
    mock_forecast = [
        {"day": 1, "date": D1, "price": 5200.0, "lower": 4900.0, "upper": 5500.0}
    ]
    monkeypatch.setattr(get_predictor(), "forecast", MagicMock(return_value=mock_forecast))
    monkeypatch.setattr(get_predictor(), "predict", MagicMock(return_value=5100.0))

    service = PredictionService()
    res = await service.predict("DEL", "BOM", FUTURE_DATE)
    
    # Assert separation of observed vs prediction
    assert res["predicted_price"] == 5100.0
    assert res["current_market"]["lowest_fare"] == 5000.0
    assert res["prediction_horizon"] == 3
    
    # Assert ForecastDay details target future fields
    fday = res["forecast"][0]
    assert fday["forecast_price"] == 5200.0
    assert "forecast_timestamp" in fday
    assert fday["prediction_horizon"] == 1
    assert "model_version" in fday
    assert "feature_schema_version" in fday
