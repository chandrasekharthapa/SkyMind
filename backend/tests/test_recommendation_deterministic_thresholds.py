"""The three recommendation thresholds, read off a served prediction.

All three call `PredictionService.predict`, so all three are gated on a servable
artifact. The thresholds themselves are asserted without a model by
`test_recommendation_policy.py`, which calls the policy directly; what is skipped
here is specifically the claim that a *served response* carries the decision the
policy would give — the wiring, not the arithmetic.
"""
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

# Dynamic future dates so this test never fails due to date drift
_today = date.today()
FUTURE_DATE = (_today + timedelta(days=30)).strftime("%Y-%m-%d")
FUTURE_DATETIME = f"{FUTURE_DATE}T14:00:00"
D1 = (_today + timedelta(days=31)).strftime("%Y-%m-%d")
D2 = (_today + timedelta(days=32)).strftime("%Y-%m-%d")
D3 = (_today + timedelta(days=33)).strftime("%Y-%m-%d")

@pytest.mark.asyncio
async def test_recommendation_thresholds_book(monkeypatch):
    """Verify forecast >5% higher triggers BOOK_NOW."""
    requires_trained_model()
    mock_flights = [
        {"flight_number": "AI101", "price": {"total": 5000.0, "currency": "INR"}, "primary_airline": "AI", "itineraries": [{"segments": [{"departure_time": FUTURE_DATETIME}]}], "seats_available": 15}
    ]
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(return_value=mock_flights))
    
    # Forecast price at day 3 is 5500.0 (>5% higher than 5000.0)
    mock_forecast = [
        {"day": 1, "date": D1, "price": 5100.0, "lower": 4800.0, "upper": 5400.0},
        {"day": 2, "date": D2, "price": 5300.0, "lower": 5000.0, "upper": 5600.0},
        {"day": 3, "date": D3, "price": 5500.0, "lower": 5200.0, "upper": 5800.0}
    ]
    monkeypatch.setattr(get_predictor(), "forecast", MagicMock(return_value=mock_forecast))
    monkeypatch.setattr(get_predictor(), "predict", MagicMock(return_value=5000.0))

    service = PredictionService()
    res = await service.predict("DEL", "BOM", FUTURE_DATE)
    
    assert res["recommendation"]["decision"] == "BOOK_NOW"

@pytest.mark.asyncio
async def test_recommendation_thresholds_wait(monkeypatch):
    """Verify forecast <5% lower triggers WAIT."""
    requires_trained_model()
    mock_flights = [
        {"flight_number": "AI101", "price": {"total": 5000.0, "currency": "INR"}, "primary_airline": "AI", "itineraries": [{"segments": [{"departure_time": FUTURE_DATETIME}]}], "seats_available": 15}
    ]
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(return_value=mock_flights))
    
    # Forecast price at day 3 is 4500.0 (<5% lower than 5000.0)
    mock_forecast = [
        {"day": 1, "date": D1, "price": 4900.0, "lower": 4600.0, "upper": 5200.0},
        {"day": 2, "date": D2, "price": 4700.0, "lower": 4400.0, "upper": 5000.0},
        {"day": 3, "date": D3, "price": 4500.0, "lower": 4200.0, "upper": 4800.0}
    ]
    monkeypatch.setattr(get_predictor(), "forecast", MagicMock(return_value=mock_forecast))
    monkeypatch.setattr(get_predictor(), "predict", MagicMock(return_value=5000.0))

    service = PredictionService()
    res = await service.predict("DEL", "BOM", FUTURE_DATE)
    
    assert res["recommendation"]["decision"] == "WAIT"

@pytest.mark.asyncio
async def test_recommendation_thresholds_monitor(monkeypatch):
    """Verify forecast with minimum today triggers BOOK_NOW."""
    requires_trained_model()
    mock_flights = [
        {"flight_number": "AI101", "price": {"total": 5000.0, "currency": "INR"}, "primary_airline": "AI", "itineraries": [{"segments": [{"departure_time": FUTURE_DATETIME}]}], "seats_available": 15}
    ]
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(return_value=mock_flights))
    
    # Forecast price at day 3 is 5100.0 (higher than 5000.0) -> BOOK_NOW today
    mock_forecast = [
        {"day": 1, "date": D1, "price": 5050.0, "lower": 4800.0, "upper": 5300.0},
        {"day": 2, "date": D2, "price": 5080.0, "lower": 4800.0, "upper": 5300.0},
        {"day": 3, "date": D3, "price": 5100.0, "lower": 4800.0, "upper": 5400.0}
    ]
    monkeypatch.setattr(get_predictor(), "forecast", MagicMock(return_value=mock_forecast))
    monkeypatch.setattr(get_predictor(), "predict", MagicMock(return_value=5000.0))

    service = PredictionService()
    res = await service.predict("DEL", "BOM", FUTURE_DATE)
    
    assert res["recommendation"]["decision"] == "BOOK_NOW"
