"""Fixes from the 2026-10-02 full evaluation run."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.evals import chat_e2e as e2e
from backend.governance.classifier import classify_message
from backend.governance.models import DomainEnum
from backend.services import chatbot_tools
from backend.services.chat_response_builder import ChatResponseBuilder
from backend.services.chat_response_validator import ChatResponseValidator as V


def test_rupee_sentences_are_removed_and_the_explanation_kept():
    answer = (
        "A Saver fare is the cheapest option but charges for changes and cancellations. "
        "A change fee is usually around ₹3,000 plus the fare difference.\n\n"
        "| Feature | Saver | Flexi |\n| --- | --- | --- |\n| Change fee | ₹3,000 | Free |\n| Refund | Partial | Higher |\n\n"
        "A Flexi fare costs more but lets you change or cancel cheaply."
    )
    trimmed = V.strip_unverified_amounts(answer)
    assert "₹" not in trimmed
    assert "Saver fare is the cheapest" in trimmed and "Flexi fare costs more" in trimmed
    assert "| Refund | Partial | Higher |" in trimmed
    assert V.validate_llm_response(trimmed, [])


@pytest.mark.parametrize("text", ["Who are you?", "What can you do?", "What can you help me with?", "Introduce yourself"])
def test_questions_about_the_assistant_are_not_off_topic(text):
    assert classify_message(text).domain != DomainEnum.UNKNOWN


async def test_tool_results_carry_the_weekday():
    class Tool:
        @staticmethod
        async def run(origin: str, destination: str, departure_date: str):
            return {"status": "success", "flights": []}

    with patch.dict(chatbot_tools.TOOL_MAP, {"fake_tool": Tool}):
        res = await chatbot_tools.execute_chatbot_tool(
            "fake_tool", {"origin": "DEL", "destination": "DXB", "departure_date": "2026-11-01"})
    assert res["departure_date_display"] == "Sunday, 1 November 2026"


FLIGHTS = [{"primary_airline": "AI", "primary_airline_name": "Air India", "price": 6000, "itineraries": []}]


async def test_one_scrape_serves_search_then_recommend_for_the_same_route(monkeypatch):
    monkeypatch.setenv("CHAT_SEARCH_CACHE_SECONDS", "600")
    search = AsyncMock(return_value=FLIGHTS)
    with patch.object(chatbot_tools.flight_search_service, "search", search):
        await chatbot_tools.SearchFlightsTool.run("DEL", "BOM", "2026-10-16")
        await chatbot_tools.SearchFlightsTool.run("DEL", "BOM", "2026-10-16", airline="Air India")
        await chatbot_tools.CompareFlightsTool.run("DEL", "BOM", "2026-10-16")
        await chatbot_tools.SearchFlightsTool.run("DEL", "BOM", "2026-10-17")
    assert search.await_count == 2  # one per distinct date


async def test_empty_results_are_not_cached_and_ttl_zero_disables(monkeypatch):
    search = AsyncMock(side_effect=[[], FLIGHTS, FLIGHTS])
    with patch.object(chatbot_tools.flight_search_service, "search", search):
        await chatbot_tools.SearchFlightsTool.run("DEL", "BOM", "2026-10-16")
        await chatbot_tools.SearchFlightsTool.run("DEL", "BOM", "2026-10-16")
        assert search.await_count == 2
        monkeypatch.setenv("CHAT_SEARCH_CACHE_SECONDS", "0")
        await chatbot_tools.SearchFlightsTool.run("DEL", "BOM", "2026-10-16")
        assert search.await_count == 3


def test_summary_shows_airline_names_not_codes():
    out = ChatResponseBuilder.build_recommendations_summary({
        "cheapest": {"primary_airline": "AI", "primary_airline_name": "AI", "price": 6314.0,
                     "departure_time": "2026-10-03T05:00:00"}})
    assert "Air India, departs 05:00 at **₹6,314**" in out
    table = ChatResponseBuilder.build_flight_search_summary(
        [{"primary_airline": "6E", "price": 10064, "itineraries": []}], "BBI", "DEL")
    assert "| IndiGo |" in table


def test_gateway_errors_are_outages_not_answers():
    transport = httpx.MockTransport(lambda req: httpx.Response(502, text=""))
    with httpx.Client(transport=transport) as client:
        r = e2e.run_case(client, "http://test", e2e.load_cases(ids=["greeting_hi"])[0], timeout=5)
    assert r.error and "502" in r.error
    assert e2e.score(e2e.load_cases(ids=["greeting_hi"])[0], r).passed is None
