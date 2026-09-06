"""An empty answer and a failed lookup must not look the same to a client.

`GET /flights/airports` used to catch every exception and return `{"airports": []}`
with HTTP 200. An empty list from a *working* lookup is a completely ordinary answer —
the user typed three letters that match no airport — so from outside the process there
was no way to tell that apart from an unreachable database, a renamed column, or a
revoked key. The frontend's autocomplete swallows failures too
(`frontend/lib/api.ts:380`, `catch { return []; }`), which is defensible for a dropdown
but means the silent 200 was the *only* signal that ever existed, and it said "success".

These tests pin the distinction rather than the wording: empty stays 200, failure
raises. They call the handler coroutine directly instead of going through a TestClient,
so they do not need an app instance or a live database.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from fastapi import HTTPException

from backend.routers.flights import search_airports_flights
from backend.database import flight_repository as flight_repository_module


@pytest.mark.asyncio
async def test_a_failed_lookup_raises_instead_of_returning_an_empty_list(monkeypatch):
    """The regression this file exists for: a raising repository must not read as 200."""
    monkeypatch.setattr(
        flight_repository_module.flight_repository, "search_airports",
        MagicMock(side_effect=RuntimeError("connection refused")),
    )

    with pytest.raises(HTTPException) as excinfo:
        await search_airports_flights(q="del")

    # 503, not 500: the query was valid and the dependency was unreachable, which is
    # what `predict.py` already uses that code for.
    assert excinfo.value.status_code == 503, excinfo.value.status_code
    # The client must be told this is not an empty result. Asserting on the substance
    # of the message, because the whole defect was a response that read as an answer.
    assert "not an empty result" in str(excinfo.value.detail), excinfo.value.detail


@pytest.mark.asyncio
async def test_the_underlying_error_is_not_leaked_to_the_client(monkeypatch):
    """The exception text belongs in the server log, not in a public response body.

    Same rule the search endpoint follows for `provider_error`: an exception repr can
    carry a hostname, a table name, or a connection string.
    """
    monkeypatch.setattr(
        flight_repository_module.flight_repository, "search_airports",
        MagicMock(side_effect=RuntimeError("postgres://user:hunter2@db.internal:5432")),
    )

    with pytest.raises(HTTPException) as excinfo:
        await search_airports_flights(q="del")

    detail = str(excinfo.value.detail)
    assert "hunter2" not in detail, detail
    assert "db.internal" not in detail, detail


@pytest.mark.asyncio
async def test_a_genuinely_empty_match_is_still_a_successful_empty_list(monkeypatch):
    """The other half of the distinction. Without this, "raise on empty" would pass too."""
    monkeypatch.setattr(
        flight_repository_module.flight_repository, "search_airports",
        MagicMock(return_value=[]),
    )

    result = await search_airports_flights(q="zzz")

    assert result == {"airports": []}, result


@pytest.mark.asyncio
async def test_matches_are_returned_with_india_and_exact_code_first(monkeypatch):
    """Existing ordering behaviour, pinned so the error-path change cannot regress it."""
    monkeypatch.setattr(
        flight_repository_module.flight_repository, "search_airports",
        MagicMock(return_value=[
            {"iata_code": "DXB", "city": "Dubai", "name": "Dubai Intl", "country": "UAE"},
            {"iata_code": "DED", "city": "Dehradun", "name": "Jolly Grant", "country": "India"},
            {"iata_code": "DEL", "city": "Delhi", "name": "Indira Gandhi Intl", "country": "India"},
        ]),
    )

    result = await search_airports_flights(q="del")

    codes = [a["iata"] for a in result["airports"]]
    # India before elsewhere, and within India the exact code match first.
    assert codes == ["DEL", "DED", "DXB"], codes
    # Every declared key is present even when the repository row uses `iata_code`.
    for airport in result["airports"]:
        assert set(airport) == {"iata", "city", "name", "country"}, airport
