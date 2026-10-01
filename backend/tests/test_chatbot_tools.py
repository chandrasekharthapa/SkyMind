import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# A departure date that is always in the future. These tests hard-coded
# "2026-07-26", which has since passed; execute_chatbot_tool now refuses past
# departure dates (see prepare_tool_args), so a fixed date would rot.
from datetime import date as _date, timedelta as _timedelta
FUTURE_DATE = (_date.today() + _timedelta(days=30)).isoformat()

from backend.services.chatbot_tools import TOOL_MAP, execute_chatbot_tool

@pytest.mark.asyncio
async def test_route_information_tool(monkeypatch):
    """Test RouteInformationTool verification is executed correctly."""
    from backend.services.flight_data_service import flight_data_service
    monkeypatch.setattr(flight_data_service, "route_supported", MagicMock(return_value=True))

    res = await execute_chatbot_tool("route_information", {"origin": "DEL", "destination": "BOM"})
    assert res["status"] == "success"
    assert res["supported"] is True

@pytest.mark.asyncio
async def test_historical_prices_tool(monkeypatch):
    """Test HistoricalPricesTool queries the decoupled repository cache."""
    from backend.database.flight_repository import flight_repository
    monkeypatch.setattr(flight_repository, "get_price_history_cache", MagicMock(return_value=[{"price": 5000}]))

    res = await execute_chatbot_tool("historical_prices", {"origin": "DEL", "destination": "BOM", "departure_date": FUTURE_DATE})
    assert res["status"] == "success"
    assert len(res["data"]) == 1
    assert res["data"][0]["price"] == 5000
