import pytest
import sys
import os
from unittest.mock import AsyncMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.chatbot_tools import execute_chatbot_tool
from backend.services.flight_search_service import flight_search_service

@pytest.mark.asyncio
async def test_search_flights_tool(monkeypatch):
    """Verify SearchFlightsTool calls FlightSearchService.search."""
    mock_search = AsyncMock(return_value=[{"flight_number": "AI101", "price": 9500}])
    monkeypatch.setattr(flight_search_service, "search", mock_search)

    res = await execute_chatbot_tool(
        "search_flights",
        {"origin": "DEL", "destination": "BOM", "departure_date": "2026-07-26"}
    )

    assert res["status"] == "success"
    assert len(res["flights"]) == 1
    assert res["flights"][0]["flight_number"] == "AI101"
    mock_search.assert_called_once()
