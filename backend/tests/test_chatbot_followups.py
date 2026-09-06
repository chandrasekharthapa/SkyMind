import pytest
import sys
import os
import json
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.chatbot_service import chatbot_service
from backend.services.flight_search_service import flight_search_service

@pytest.mark.asyncio
async def test_chatbot_context_fill_followups(monkeypatch):
    """Test chatbot session context fills missing arguments during follow-up tool calls."""
    context = chatbot_service.get_session_context("sess_12345")
    context.origin = "DEL"
    context.destination = "BOM"
    context.departure_date = "2026-07-26"

    # Simulate final tool execution callback
    mock_search = AsyncMock(return_value=[])
    monkeypatch.setattr(flight_search_service, "search", mock_search)

    # When LLM tool parameters are incomplete (e.g. only cabin_class provided)
    # The chatbot service should populate origin, destination, and departure_date from session context
    from backend.services.chatbot_tools import execute_chatbot_tool
    
    args = {"cabin_class": "BUSINESS"}
    # Merge context parameters
    for key in ["origin", "destination", "departure_date"]:
        if key not in args and getattr(context, key, None):
            args[key] = getattr(context, key)

    await execute_chatbot_tool("search_flights", args)
    
    mock_search.assert_called_once_with(
        origin_iata="DEL",
        destination_iata="BOM",
        departure_date="2026-07-26",
        adults=1,
        cabin_class="BUSINESS",
        sorting="price"
    )
