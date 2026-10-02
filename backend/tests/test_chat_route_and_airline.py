"""Airport abbreviations, airline filtering, and the fallback table's columns."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.services import chatbot_tools
from backend.services.chat_response_builder import ChatResponseBuilder
from backend.services.chatbot_service import _build_system_prompt
from backend.services.intent_planner import normalize_airport_code


@pytest.mark.parametrize("text, code", [
    ("BBSR", "BBI"), ("bbsr", "BBI"), ("Bhubaneswar", "BBI"), ("Bhubaneswar Airport", "BBI"),
    ("delhi", "DEL"), ("Gurgaon", "DEL"), ("TVM", "TRV"), ("Trivandrum", "TRV"),
    ("BOM", "BOM"), ("Jaipur", "JAI"), ("Atlantis", None), ("", None),
])
def test_airport_names_and_abbreviations(text, code):
    assert normalize_airport_code(text) == code


@pytest.mark.parametrize("text, code", [
    ("Air India", "AI"), ("air india express", "IX"), ("AI", "AI"), ("IndiGo", "6E"),
    ("6E", "6E"), ("Vistara", "AI"), ("akasa", "QP"), ("spicejet", "SG"), ("Lufthansa", None),
])
def test_resolve_airline(text, code):
    assert chatbot_tools.resolve_airline(text) == code


def _flight(code, name, price):
    return {"primary_airline": code, "primary_airline_name": name, "price": price, "itineraries": []}


FLIGHTS = [_flight("6E", "IndiGo", 11155), _flight("AI", "Air India", 12890), _flight("IX", "Air India Express", 9900)]


async def _search(airline):
    with patch.object(chatbot_tools.flight_search_service, "search", AsyncMock(return_value=FLIGHTS)):
        return await chatbot_tools.SearchFlightsTool.run("DEL", "BBI", "2026-10-03", airline=airline)


async def test_airline_filter_keeps_only_that_carrier():
    res = await _search("Air India")
    assert [f["primary_airline"] for f in res["flights"]] == ["AI"]   # not Air India Express


async def test_airline_with_no_flights_says_so_instead_of_showing_others():
    res = await _search("Akasa")
    assert res["flights"] == [] and "No Akasa flights" in res["note"] and "IndiGo" in res["note"]


async def test_no_airline_returns_everything():
    assert len((await _search(None))["flights"]) == 3


def test_table_shows_real_stops_and_readable_duration():
    f = {"primary_airline_name": "IndiGo", "price_display": "₹11,155",
         "itineraries": [{"duration": "PT350M", "segments": [
             {"departure_time": "2026-10-03T05:55:00", "stops": 1}]}]}
    row = ChatResponseBuilder.build_flight_search_summary([f], "DEL", "BBI").splitlines()[-1]
    assert "| 5h 50m | 1 |" in row and "05:55" in row


def test_non_stop_label_and_short_durations():
    assert ChatResponseBuilder.format_duration("PT2H5M") == "2h 05m"
    assert ChatResponseBuilder.format_duration("PT45M") == "45m"
    assert ChatResponseBuilder.format_duration(None) is None
    f = {"itineraries": [{"duration": "PT130M", "segments": [{"stops": 0}]}], "price": 1}
    assert "| 2h 10m | Non-stop |" in ChatResponseBuilder.build_flight_search_summary([f], "A", "B")


def test_prompt_spells_out_tomorrow():
    prompt = _build_system_prompt()
    assert "tomorrow is" in prompt and "BBSR" in prompt
