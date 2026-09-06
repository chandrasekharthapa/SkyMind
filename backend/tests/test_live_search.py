import sys
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

# Add backend and workspace root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.main import app
from backend.services.flight_data_service import flight_data_service
from backend.database.database import database as db

client = TestClient(app)

@pytest.mark.asyncio
async def test_live_search_success(monkeypatch):
    """Test that live search processes raw flights correctly when MCP succeeds."""
    mock_search = AsyncMock(return_value={
        "data": [
            {
                "price": 7500.555,
                "currency": "INR",
                "primary_airline": "6E",
                "legs": [{"flight_number": "6261", "airline_code": "6E"}]
            }
        ]
    })
    monkeypatch.setattr(flight_data_service, "search_flights", mock_search)

    response = client.post("/live-search", json={
        "origin": "DEL",
        "destination": "BOM",
        "departure_date": "2026-07-09"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "flights" in data
    assert len(data["flights"]) == 1
    flight = data["flights"][0]
    
    # Assert exact frontend key mapping
    assert flight["origin_code"] == "DEL"
    assert flight["destination_code"] == "BOM"
    assert flight["airline_code"] == "6E"
    assert flight["flight_number"] == "6E6261"
    assert flight["price"] == 7500.56  # Rounded to 2 decimals
    assert flight["seats_available"] == 9


@pytest.mark.asyncio
async def test_live_search_fallback(monkeypatch):
    """Test that live search falls back to Supabase historical cache when MCP returns empty."""
    # Mock live transport to return empty
    mock_search = AsyncMock(return_value={"data": []})
    monkeypatch.setattr(flight_data_service, "search_flights", mock_search)

    # Mock Supabase database client query
    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.execute.return_value = MagicMock(data=[
        {
            "origin_code": "DEL",
            "destination_code": "BOM",
            "airline_code": "AI",
            "flight_number": "AI101",
            "price": 8200.777,
            "is_live": True,
            "recorded_at": "2026-07-06T12:00:00"
        }
    ])
    
    monkeypatch.setattr(db.supabase, "table", MagicMock(return_value=mock_query))

    response = client.post("/live-search", json={
        "origin": "DEL",
        "destination": "BOM",
        "departure_date": "2026-07-09"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "flights" in data
    assert len(data["flights"]) == 1
    flight = data["flights"][0]
    
    # Assert exact frontend key mapping from fallback
    assert flight["origin_code"] == "DEL"
    assert flight["destination_code"] == "BOM"
    assert flight["airline_code"] == "AI"
    assert flight["flight_number"] == "AI101"
    assert flight["price"] == 8200.78  # Rounded to 2 decimals
    assert flight["seats_available"] == 9
    
    # Verify mock queries and filters
    mock_query.eq.assert_any_call("origin_code", "DEL")
    mock_query.eq.assert_any_call("destination_code", "BOM")
    mock_query.eq.assert_any_call("is_live", True)
