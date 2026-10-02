"""Flight numbers are not fares, and the fallback summary reads like an answer."""

import pytest

from backend.services.chat_response_builder import ChatResponseBuilder
from backend.services.chat_response_validator import ChatResponseValidator as V

TOOL = [{"status": "success", "flights": [{"price": 6913, "flight_number": "AI 2671"},
                                          {"price": 7017, "flight_number": "6E2134"}]}]


@pytest.mark.parametrize("text", [
    "The cheapest is Air India AI 2671 at ₹6,913.",
    "IndiGo 6E2134 departs at 06:10 for ₹7,017.",
    "Akasa QP-1407 is sold out; AI 2671 costs ₹6,913.",
])
def test_flight_numbers_are_not_read_as_fares(text):
    assert V.validate_llm_response(text, TOOL) is True


@pytest.mark.parametrize("text", [
    "The cheapest is AI 2671 at ₹5,500.",   # invented fare next to a real flight
    "Fares start from 5500 on this route.",  # bare invented fare
])
def test_invented_fares_are_still_caught(text):
    assert V.validate_llm_response(text, TOOL) is False


def test_lowercase_words_before_numbers_are_not_flight_numbers():
    assert 5500.0 in V.extract_prices("fares in 5500 range")


def test_recommendations_summary_formats_price_and_skips_missing_flight_number():
    out = ChatResponseBuilder.build_recommendations_summary({
        "cheapest": {"primary_airline_name": "Air India", "flight_number": None, "price": 6913.0,
                     "departure_time": "2026-10-16T06:10:00"},
        "fastest": {"primary_airline_name": "Air India Express", "flight_number": "IX 1234",
                    "price": 7017.0, "currency": "INR"},
    })
    assert "Air India, departs 06:10 at **₹6,913**" in out
    assert "Air India Express IX 1234 at **₹7,017**" in out
    assert "None" not in out and "6913.0" not in out


@pytest.mark.parametrize("text", [
    "The cheapest is AI 2671 at ₹6,913. Check the airline's baggage policy before you fly.",
    "IndiGo at ₹7,017. Baggage allowance may vary by fare type.",
    "AI 2671 at ₹6,913. Confirm your terminal on the boarding pass.",
])
def test_advice_to_check_a_detail_is_not_an_invented_detail(text):
    assert V.validate_llm_response(text, TOOL) is True


@pytest.mark.parametrize("text", [
    "AI 2671 at ₹6,913 includes 15 kg free baggage.",
    "AI 2671 at ₹6,913 departs from Terminal 3, gate 12.",
    "Book AI 2671 at ₹6,913 and get a 10% discount.",
])
def test_asserted_details_are_still_rejected(text):
    assert V.validate_llm_response(text, TOOL) is False


def test_table_drops_columns_that_are_empty_on_every_row_and_shows_arrival():
    f = {"primary_airline_name": "IndiGo", "price": 11992, "itineraries": [{"duration": "PT385M", "segments": [
        {"departure_time": "2026-10-03T20:20:00", "arrival_time": "2026-10-04T02:45:00", "stops": 1}]}]}
    table = ChatResponseBuilder.build_flight_search_summary([f], "BBI", "DEL")
    header, row = table.splitlines()[2], table.splitlines()[-1]
    assert header == "| Airline | Departs | Arrives | Duration | Stops | Price |"
    assert row == "| IndiGo | 20:20 | 02:45 +1 | 6h 25m | 1 | ₹11,992 |"
    assert "N/A" not in table and "MONITOR" not in table
