import pytest
import sys
import os
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.prediction_service import prediction_service, PredictionValidator
from backend.services.flight_search_service import flight_search_service
from backend.tests.model_availability import requires_trained_model

# Dynamic future date so this test never fails due to date drift
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
FUTURE_DATETIME = f"{FUTURE_DATE}T14:00:00"

@pytest.mark.asyncio
async def test_prediction_service_orchestration(monkeypatch):
    """Test E2E predict flow handles resolution, ML predict, and formatting.

    Gated on a servable artifact — the three validator tests below are not, because
    input validation runs before the capability precondition and holds with no model
    loaded. That split is the point of the gate: it must not switch off the tests
    that would still catch a regression here.
    """
    requires_trained_model()

    mock_flights = [
        {
            "flight_number": "AI101",
            "price": {"total": 8500.0, "currency": "INR"},
            "primary_airline": "AI",
            "itineraries": [{"segments": [{"departure_time": FUTURE_DATETIME}]}],
            "seats_available": 15
        }
    ]
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(return_value=mock_flights))
    monkeypatch.setattr(prediction_service.repository, "get_price_history_cache", MagicMock(return_value=[]))

    res = await prediction_service.predict(
        origin="DEL",
        destination="BOM",
        departure_date=FUTURE_DATE
    )

    assert "predicted_price" in res
    assert "forecast" in res
    assert "recommendation" in res
    assert "search_metadata" in res
    assert "market_snapshot" in res
    assert res["search_metadata"]["flight_count"] == 1

def test_prediction_validator_invalid_iata():
    with pytest.raises(ValueError, match="Origin IATA code"):
        PredictionValidator.validate_request("DELHI", "BOM", FUTURE_DATE)

def test_prediction_validator_same_route():
    with pytest.raises(ValueError, match="Origin and destination must differ"):
        PredictionValidator.validate_request("DEL", "DEL", FUTURE_DATE)

def test_prediction_validator_past_date():
    with pytest.raises(ValueError, match="Departure date must be in the future"):
        PredictionValidator.validate_request("DEL", "BOM", "2020-01-01")
