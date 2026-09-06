import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database.flight_repository import SupabaseFlightRepository


def _mock_query(rows):
    """A stand-in for the Supabase query builder, recording every filter."""
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.return_value = MagicMock(data=rows)
    return query


def test_repository_get_price_history_cache(monkeypatch):
    repository = SupabaseFlightRepository()
    mock_supabase_query = _mock_query([{"price": 8200}])

    from backend.database.database import database as db
    monkeypatch.setattr(db.supabase, "table", MagicMock(return_value=mock_supabase_query))

    res = repository.get_price_history_cache("DEL", "BOM", "2026-07-26", 10)
    assert len(res) == 1
    assert res[0]["price"] == 8200


def test_a_route_query_filters_on_the_route_only(monkeypatch):
    """The four positional callers must keep getting every carrier's rows.

    `flight_search_service`'s cache and `chatbot_tools`' route-level trend answer
    are about the route, not one flight, so the two curve filters are keyword-only
    and default to None — and when they are not passed, no carrier filter may
    reach the query.
    """
    repository = SupabaseFlightRepository()
    query = _mock_query([])

    from backend.database.database import database as db
    monkeypatch.setattr(db.supabase, "table", MagicMock(return_value=query))

    repository.get_price_history_cache("DEL", "BOM", "2026-07-26", 100)

    filtered = [call.args[0] for call in query.eq.call_args_list]
    assert filtered == ["origin_code", "destination_code", "departure_date"]


def test_a_curve_query_filters_on_the_flight_being_quoted(monkeypatch):
    """Why the filters exist: `max_results` is applied before any Python narrowing.

    `price_changes_from_records` narrows to one booking curve *after* this query
    has already discarded rows, so the newest 100 route-wide rows could contain
    nought to two observations of the flight being priced — and the movement
    features then came out NaN while the refusal quoted the route's count. The cap
    only bounds the right population if the identity reaches the database.
    """
    repository = SupabaseFlightRepository()
    query = _mock_query([{"price": 5000}])

    from backend.database.database import database as db
    monkeypatch.setattr(db.supabase, "table", MagicMock(return_value=query))

    res = repository.get_price_history_cache(
        "DEL", "BOM", "2026-07-26", 100,
        airline_code="6E", flight_number="6E101",
    )

    assert res == [{"price": 5000}]
    assert dict(call.args for call in query.eq.call_args_list) == {
        "origin_code": "DEL",
        "destination_code": "BOM",
        "departure_date": "2026-07-26",
        "airline_code": "6E",
        "flight_number": "6E101",
    }
    query.limit.assert_called_once_with(100)


def test_a_carrier_without_a_flight_number_narrows_only_as_far_as_it_can(monkeypatch):
    """A live snapshot may name an airline and no flight number.

    The query should then be as narrow as the identity actually known and no
    narrower, rather than dropping the carrier filter too or inventing a number.
    """
    repository = SupabaseFlightRepository()
    query = _mock_query([])

    from backend.database.database import database as db
    monkeypatch.setattr(db.supabase, "table", MagicMock(return_value=query))

    repository.get_price_history_cache(
        "DEL", "BOM", "2026-07-26", 100, airline_code="6E", flight_number=None,
    )

    filtered = [call.args[0] for call in query.eq.call_args_list]
    assert filtered == [
        "origin_code", "destination_code", "departure_date", "airline_code",
    ]


def test_a_failed_query_returns_no_rows_rather_than_raising(monkeypatch):
    """Five callers treat this as a cache, so an outage must not take search down.

    The empty list is indistinguishable downstream from "no observations
    recorded", which is why the failure is logged: a refusal that names an
    observation count is only accurate when nothing was logged here.
    """
    repository = SupabaseFlightRepository()

    from backend.database.database import database as db
    monkeypatch.setattr(
        db.supabase, "table",
        MagicMock(side_effect=RuntimeError("connection reset")),
    )

    assert repository.get_price_history_cache("DEL", "BOM", "2026-07-26", 100) == []
