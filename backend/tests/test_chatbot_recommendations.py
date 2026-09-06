import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.chatbot_tools import execute_chatbot_tool
from backend.services.flight_search_service import flight_search_service
from backend.services.recommendation_engine import RecommendationEngine

@pytest.mark.asyncio
async def test_recommend_flights_tool(monkeypatch):
    """Verify RecommendFlightsTool extracts and highlights the options via RecommendationEngine."""
    mock_search_res = [
        {"flight_number": "6E101", "price": 5000.0, "primary_airline": "6E", "primary_airline_name": "IndiGo", "currency": "INR", "itineraries": [{"duration": "PT2H", "segments": [{"flight_number": "6E101", "origin": "DEL", "destination": "BOM", "departure_time": "2026-07-26T08:00:00", "arrival_time": "2026-07-26T10:00:00", "airline_code": "6E", "airline_name": "IndiGo"}]}]},
        {"flight_number": "AI202", "price": 9000.0, "primary_airline": "AI", "primary_airline_name": "Air India", "currency": "INR", "itineraries": [{"duration": "PT1H15M", "segments": [{"flight_number": "AI202", "origin": "DEL", "destination": "BOM", "departure_time": "2026-07-26T09:00:00", "arrival_time": "2026-07-26T10:15:00", "airline_code": "AI", "airline_name": "Air India"}]}]}
    ]
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(return_value=mock_search_res))

    res = await execute_chatbot_tool(
        "recommend_flights",
        {"origin": "DEL", "destination": "BOM", "departure_date": "2026-07-26"}
    )

    assert res["status"] == "success"
    # Cheapest should be 6E101
    assert res["cheapest"]["flight_number"] == "6E101"
    # Fastest should be AI202 (1h15m vs 2h)
    assert res["fastest"]["flight_number"] == "AI202"
