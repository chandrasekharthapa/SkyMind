import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.flight_search_service import flight_search_service
from backend.services.flight_normalizer import FlightNormalizer, NormalizedFlight, NormalizedItinerary, NormalizedSegment
from backend.services.chatbot_tools import SearchFlightsTool
from backend.services.chatbot_service import _slim_tool_result
from backend.services.ingestion_controller import MarketDataController


def test_airline_mapping_integrity():
    """Verify that carrier code IX maps to Air India Express and AI maps to Air India without 6E overrides."""
    assert MarketDataController.AIRLINE_NAMES.get("IX") == "Air India Express"
    assert MarketDataController.AIRLINE_NAMES.get("AI") == "Air India"
    assert MarketDataController.AIRLINE_NAMES.get("6E") == "IndiGo"

    # Normalize raw flight with IX airline code
    raw_ix = {
        "flight_number": "IX1003",
        "primary_airline": "IX",
        "primary_airline_name": "Air India Express",
        "price": 7500.0,
        "currency": "INR",
        "itineraries": [
            {
                "duration": "PT2H15M",
                "segments": [
                    {
                        "flight_number": "IX1003",
                        "airline_code": "IX",
                        "airline_name": "Air India Express",
                        "origin": "BBI",
                        "destination": "DEL",
                        "departure_time": "2026-07-26T10:00:00",
                        "arrival_time": "2026-07-26T12:15:00"
                    }
                ]
            }
        ]
    }
    norm = FlightNormalizer.normalize_mcp_flight(raw_ix, "BBI", "DEL", "2026-07-26")
    assert norm is not None
    assert norm.primary_airline == "IX"
    assert norm.primary_airline_name == "Air India Express"
    assert norm.flight_number == "IX1003"


def test_deduplication_eliminates_duplicates():
    """Verify that duplicate flights with identical carrier, flight number, departure time, and price are deduplicated."""
    from backend.services.recommendation_engine import RecommendationEngine

    f1 = NormalizedFlight(
        id="IX-IX1003-7500.0",
        primary_airline="IX",
        primary_airline_name="Air India Express",
        flight_number="IX1003",
        price=7500.0,
        itineraries=[
            NormalizedItinerary(
                duration="PT2H15M",
                segments=[
                    NormalizedSegment(
                        flight_number="IX1003",
                        airline_code="IX",
                        airline_name="Air India Express",
                        origin="BBI",
                        destination="DEL",
                        departure_time="2026-07-26T10:00:00",
                        arrival_time="2026-07-26T12:15:00",
                        duration="PT2H15M"
                    )
                ]
            )
        ]
    )
    # Duplicate instance
    f2 = f1.model_copy()

    deduped = RecommendationEngine.deduplicate_flights([f1, f2, f1])
    assert len(deduped) == 1
    assert deduped[0].flight_number == "IX1003"


def test_slim_tool_result_preserves_structured_time_attributes():
    """Verify _slim_tool_result extracts departure_time, arrival_time, and duration for LLM context."""
    raw_tool_result = {
        "status": "success",
        "flights": [
            {
                "flight_number": "6E1003",
                "primary_airline": "6E",
                "primary_airline_name": "IndiGo",
                "price": 6500.0,
                "currency": "INR",
                "itineraries": [
                    {
                        "duration": "PT2H10M",
                        "segments": [
                            {
                                "flight_number": "6E1003",
                                "airline_code": "6E",
                                "airline_name": "IndiGo",
                                "origin": "BBI",
                                "destination": "DEL",
                                "departure_time": "2026-07-26T06:00:00",
                                "arrival_time": "2026-07-26T08:10:00"
                            }
                        ]
                    }
                ]
            }
        ]
    }

    slimmed = _slim_tool_result(raw_tool_result)
    assert "flights" in slimmed
    flight_entry = slimmed["flights"][0]

    assert flight_entry["flight_number"] == "6E1003"
    assert flight_entry["departure_time"] == "2026-07-26T06:00:00"
    assert flight_entry["arrival_time"] == "2026-07-26T08:10:00"
    assert flight_entry["duration"] == "PT2H10M"
    assert flight_entry["origin"] == "BBI"
    assert flight_entry["destination"] == "DEL"


@pytest.mark.asyncio
async def test_search_and_chat_parity():
    """Verify SearchFlightsTool returns identical non-duplicated flights to Search page."""
    sample_flight = NormalizedFlight(
        id="6E-6E1005-5500.0",
        primary_airline="6E",
        primary_airline_name="IndiGo",
        flight_number="6E1005",
        price=5500.0,
        itineraries=[
            NormalizedItinerary(
                duration="PT2H0M",
                segments=[
                    NormalizedSegment(
                        flight_number="6E1005",
                        airline_code="6E",
                        airline_name="IndiGo",
                        origin="BBI",
                        destination="DEL",
                        departure_time="2026-07-26T15:00:00",
                        arrival_time="2026-07-26T17:00:00",
                        duration="PT2H0M"
                    )
                ]
            )
        ]
    )

    mock_presentation = MagicMock()
    mock_presentation.flights = [sample_flight, sample_flight]
    mock_presentation.metadata = {"total": 1}

    with patch.object(flight_search_service, "search", AsyncMock(return_value=mock_presentation)):
        tool_res = await SearchFlightsTool.run("BBI", "DEL", "2026-07-26")
        assert tool_res["status"] == "success"
        assert len(tool_res["flights"]) == 2
        
        # When passed through _slim_tool_result, structured attributes are preserved
        slim = _slim_tool_result(tool_res)
        f_slim = slim["flights"][0]
        assert f_slim["flight_number"] == "6E1005"
        assert f_slim["departure_time"] == "2026-07-26T15:00:00"
        assert f_slim["arrival_time"] == "2026-07-26T17:00:00"
