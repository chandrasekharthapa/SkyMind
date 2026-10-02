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
