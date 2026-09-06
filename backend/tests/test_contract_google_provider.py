import pytest
from unittest.mock import AsyncMock, patch
from backend.services.flight_data_provider import GoogleFlightsProvider

@pytest.mark.asyncio
async def test_google_flights_provider_contract():
    """Verify that GoogleFlightsProvider complies with FlightDataProvider interface contract."""
    provider = GoogleFlightsProvider()
    assert provider.provider_name == "Google Flights MCP"
    
    # Mock underlying search service call
    mock_results = [{"flight_number": "6E-101", "price": {"total": 5000.0}}]
    with patch("backend.services.flight_search_service.flight_search_service.search", AsyncMock(return_value=mock_results)) as mock_search:
        res = await provider.search("DEL", "BOM", "2026-07-26")
        assert len(res) == 1
        assert res[0]["price"]["total"] == 5000.0
        mock_search.assert_called_once_with(
            origin_iata="DEL",
            destination_iata="BOM",
            departure_date="2026-07-26",
            adults=1,
            cabin_class="ECONOMY",
            sorting="price"
        )
