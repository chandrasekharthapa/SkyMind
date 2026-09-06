import pytest
import sys
import os
import math
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

@pytest.mark.asyncio
async def test_forecast_no_current_price_echo(monkeypatch):
    """Verify predicted price is model-driven and does not simply echo current live fare.

    Gated on a servable artifact. Patching `predict` is not enough to make this
    runnable: `PredictionService.predict` checks
    `model_registry.supports_forecasting` before it does any work, and that answer
    comes from what `load()` accepted — so with the three shipped artifacts
    quarantined the request is refused with `PredictionUnavailable` and the mocked
    8200.0 is never reached. The subject here is a number the model produces, which
    is exactly the case `requires_trained_model` exists for; without the gate this
    read as a broken echo-suppression feature rather than an inapplicable test.
    """
    requires_trained_model()

    mock_flights = [
        {
            "flight_number": "AI101",
            "price": {"total": 5000.0, "currency": "INR"},
            "primary_airline": "AI",
            "itineraries": [{"segments": [{"departure_time": FUTURE_DATETIME}]}],
            "seats_available": 15
        }
    ]
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(return_value=mock_flights))
    
    # Force PricePredictor to predict 8200.0 (which is different from live fare 5000.0)
    monkeypatch.setattr(get_predictor(), "predict", MagicMock(return_value=8200.0))
    
    service = PredictionService()
    res = await service.predict("DEL", "BOM", FUTURE_DATE)
    
    # Assert predicted price is model's pure output, not faked/scaled to current lowest fare
    assert res["predicted_price"] == 8200.0
    assert res["current_market"]["lowest_fare"] == 5000.0
    assert res["predicted_price"] != res["current_market"]["lowest_fare"]
