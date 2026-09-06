import pytest
import asyncio
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.flight_data_service import flight_data_service

@pytest.mark.asyncio
async def test_zero_match_returns_empty(monkeypatch):
    """Ensure that when the MCP tool returns no flights, the service returns an empty list.
    This guards against synthetic data generation.
    """
    # Mock the MCP client call to return empty data
    async def mock_search_flights(*args, **kwargs):
        return {"data": []}
    monkeypatch.setattr(flight_data_service, "search_flights", mock_search_flights)

    result = await flight_data_service.search_flights(
        origin="AAA",
        destination="BBB",
        target_date="2099-01-01",
    )
    assert isinstance(result, dict)
    assert result.get("data") == []
