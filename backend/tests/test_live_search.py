from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.database.database import database as db
from backend.main import app
from backend.services.flight_data_service import (
    STATUS_EMPTY,
    STATUS_ERROR,
    STATUS_OK,
    flight_data_service,
)


client = TestClient(app)


def _query(rows=None, error=None):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.is_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    if error is None:
        query.execute.return_value = MagicMock(data=rows or [])
    else:
        query.execute.side_effect = error
    return query


def _install_cache(monkeypatch, rows=None, error=None):
    query = _query(rows, error)
    table = MagicMock(return_value=query)
    monkeypatch.setattr(db.supabase, "table", table)
    return table, query


def _request(**overrides):
    body = {
        "origin": "DEL",
        "destination": "BOM",
        "departure_date": "2099-07-09",
    }
    body.update(overrides)
    return body


def _provider_flight():
    return {
        "price": 7500.555,
        "currency": "INR",
        "primary_airline": "6E",
        "legs": [{"flight_number": "6261", "airline_code": "6E"}],
    }


def _cache_flight():
    return {
        "airline_code": "AI",
        "flight_number": "AI101",
        "price": 8200.777,
        "currency": "INR",
        "is_synthetic": False,
        "is_live": True,
        "recorded_at": "2026-07-06T12:00:00Z",
    }


def test_live_search_maps_provider_values_and_forwards_complete_request(monkeypatch):
    mock_search = AsyncMock(return_value={
        "data": [_provider_flight()],
        "status": STATUS_OK,
        "attempts": 1,
    })
    monkeypatch.setattr(flight_data_service, "search_flights", mock_search)
    table, _ = _install_cache(monkeypatch)

    response = client.post("/live-search", json=_request(
        adults=2, children=1, infants=1, cabin_class="business"
    ))

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["provider_status"] == STATUS_OK
    assert data["data_source"] == "live_provider"
    assert data["cache_error_kind"] is None
    assert len(data["flights"]) == 1
    flight = data["flights"][0]
    assert flight["origin_code"] == "DEL"
    assert flight["destination_code"] == "BOM"
    assert flight["airline_code"] == "6E"
    assert flight["flight_number"] is None
    assert flight["price"] == 7500.56
    assert flight["currency"] == "INR"
    assert flight["seats_available"] is None
    assert flight["provenance"] == "LIVE_GOOGLE_FLIGHTS"
    assert flight["legs"] == [
        {"flight_number": "6261", "airline_code": "6E"}
    ]
    mock_search.assert_awaited_once_with(
        origin="DEL",
        destination="BOM",
        target_date="2099-07-09",
        return_date=None,
        adults=2,
        children=1,
        infants=1,
        cabin_class="BUSINESS",
        max_results=50,
        currency="INR",
    )
    table.assert_not_called()


def test_empty_provider_uses_exact_authentic_cache_slice(monkeypatch):
    monkeypatch.setattr(
        flight_data_service,
        "search_flights",
        AsyncMock(return_value={
            "data": [], "status": STATUS_EMPTY, "attempts": 1
        }),
    )
    table, query = _install_cache(monkeypatch, [_cache_flight()])

    response = client.post("/live-search", json=_request())

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["provider_status"] == STATUS_EMPTY
    assert data["data_source"] == "cache"
    assert data["flights"][0]["provenance"] == "AUTHENTIC_PRICE_HISTORY"
    assert data["flights"][0]["currency"] == "INR"
    table.assert_called_once_with("price_history")
    query.eq.assert_any_call("origin_code", "DEL")
    query.eq.assert_any_call("destination_code", "BOM")
    query.eq.assert_any_call("departure_date", "2099-07-09")
    query.is_.assert_any_call("is_synthetic", False)
    query.is_.assert_any_call("is_live", True)


@pytest.mark.parametrize("cache_rows", [[], None])
def test_provider_failure_is_not_relabelled_empty(monkeypatch, cache_rows):
    monkeypatch.setattr(
        flight_data_service,
        "search_flights",
        AsyncMock(return_value={
            "data": [],
            "status": STATUS_ERROR,
            "error_kind": "timeout",
            "attempts": 3,
        }),
    )
    _install_cache(monkeypatch, cache_rows)

    response = client.post("/live-search", json=_request())

    assert response.status_code == 200
    assert response.json() == {
        "flights": [],
        "status": "error",
        "provider_status": STATUS_ERROR,
        "provider_error_kind": "timeout",
        "provider_attempts": 3,
        "data_source": None,
        "cache_error_kind": None,
    }


def test_provider_failure_with_cache_is_explicitly_degraded(monkeypatch):
    monkeypatch.setattr(
        flight_data_service,
        "search_flights",
        AsyncMock(return_value={
            "data": [],
            "status": STATUS_ERROR,
            "error_kind": "transport",
            "attempts": 2,
        }),
    )
    _install_cache(monkeypatch, [_cache_flight()])

    response = client.post("/live-search", json=_request())

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "degraded"
    assert data["provider_status"] == STATUS_ERROR
    assert data["provider_error_kind"] == "transport"
    assert data["data_source"] == "cache"
    assert len(data["flights"]) == 1


def test_provider_and_cache_failure_remain_distinguishable(monkeypatch):
    monkeypatch.setattr(
        flight_data_service,
        "search_flights",
        AsyncMock(return_value={
            "data": [],
            "status": STATUS_ERROR,
            "error_kind": "provider",
            "attempts": 1,
        }),
    )
    _install_cache(monkeypatch, error=RuntimeError("cache unavailable"))

    response = client.post("/live-search", json=_request())

    data = response.json()
    assert data["status"] == "error"
    assert data["provider_status"] == STATUS_ERROR
    assert data["provider_error_kind"] == "provider"
    assert data["cache_error_kind"] == "RuntimeError"


def test_invalid_transport_contract_is_an_error_not_an_empty_market(monkeypatch):
    monkeypatch.setattr(
        flight_data_service,
        "search_flights",
        AsyncMock(return_value={"data": []}),
    )
    _install_cache(monkeypatch, [])

    response = client.post("/live-search", json=_request())

    data = response.json()
    assert data["status"] == "error"
    assert data["provider_status"] == STATUS_ERROR
    assert data["provider_error_kind"] == "contract"


def test_round_trip_is_refused_before_provider_or_cache_call(monkeypatch):
    search = AsyncMock()
    monkeypatch.setattr(flight_data_service, "search_flights", search)
    table, _ = _install_cache(monkeypatch)

    response = client.post(
        "/live-search",
        json=_request(return_date="2099-07-12"),
    )

    assert response.status_code == 501
    search.assert_not_awaited()
    table.assert_not_called()


@pytest.mark.parametrize(
    "patch, expected_detail",
    [
        ({"origin": "DE1"}, "Airport codes"),
        ({"destination": "DEL"}, "Origin and destination"),
        ({"departure_date": "2099-02-30"}, "valid date"),
        ({"return_date": "2099-07-08"}, "return_date"),
        ({"adults": 0}, "greater than or equal to 1"),
        ({"infants": 2}, "Infants cannot exceed adults"),
        ({"adults": 5, "children": 5}, "Total passengers"),
        ({"cabin_class": "cargo"}, "cabin_class"),
        ({"unexpected": True}, "Extra inputs"),
    ],
)
def test_invalid_request_is_rejected_without_provider_call(
    monkeypatch, patch, expected_detail
):
    search = AsyncMock()
    monkeypatch.setattr(flight_data_service, "search_flights", search)

    response = client.post("/live-search", json=_request(**patch))

    assert response.status_code == 422
    assert expected_detail in str(response.json())
    search.assert_not_awaited()
