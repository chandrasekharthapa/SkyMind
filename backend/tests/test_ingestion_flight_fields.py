"""Stops, duration and arrival time reach price_history (October 2026).

The scraper read all three from every card; none was stored. `duration` was
looked up under the wrong key (`duration` vs the scraper's `duration_minutes`),
`arrival_time` was never passed on, and `stops` was NULL because the zero-stop
check matched only the US "Nonstop", not the en-IN "Non-stop" (that half is
tested in india-flight-mcp/test/cardParsing.test.js). Every stored row therefore
lacked the stop count, which left the model's direct/connecting-ratio features
empty in training.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.services.flight_data_service import STATUS_OK
from backend.services.flight_search_service import flight_search_service
from backend.services.historical_data_service import historical_data_service
from backend.services.ingestion_controller import MarketDataController

DEP = (date.today() + timedelta(days=20)).isoformat()


def _payload(**over):
    kw = dict(origin_code="DEL", destination_code="BOM", airline_code="6E",
              price=5500.0, departure_date=DEP, days_until_dep=20, currency="INR",
              departure_time=f"{DEP}T06:10:00")
    kw.update(over)
    return MarketDataController.get_db_payload(MarketDataController.format_payload(**kw))


def test_arrival_time_is_stored_and_normalised():
    row = _payload(arrival_time=f"{DEP}T08:25:00")
    assert row["arrival_time"] == f"{DEP}T08:25:00"
    # A bare clock time is anchored to the departure date, as for departure_time.
    assert _payload(arrival_time="08:25")["arrival_time"].startswith(DEP)


def test_overnight_arrival_keeps_its_next_day_date():
    nxt = (date.fromisoformat(DEP) + timedelta(days=1)).isoformat()
    row = _payload(departure_time=f"{DEP}T23:40:00", arrival_time=f"{nxt}T01:55:00")
    assert row["arrival_time"].startswith(nxt)


def test_unknown_fields_stay_absent_not_invented():
    row = _payload()
    assert "arrival_time" not in row and "duration" not in row and "stops" not in row


@pytest.mark.asyncio
async def test_scraped_fields_reach_the_insert():
    provider = {"status": STATUS_OK, "data": [
        {"price": 6200.0, "currency": "INR", "primary_airline": "6E",
         "departure_time": f"{DEP}T06:10:00", "arrival_time": f"{DEP}T08:25:00",
         "duration_minutes": 135, "stops": 0},
        {"price": 7400.0, "currency": "INR", "primary_airline": "AI",
         "departure_time": f"{DEP}T09:00:00", "arrival_time": f"{DEP}T13:05:00",
         "duration_minutes": 245, "stops": 1},
        {"price": 6900.0, "currency": "INR", "primary_airline": "QP",
         "departure_time": f"{DEP}T11:00:00", "duration_minutes": 55, "stops": None},
    ]}
    with (
        patch("backend.services.flight_data_service.flight_data_service.search_flights",
              return_value=provider),
        patch("backend.services.historical_data_service.historical_data_service."
              "insert_observations", return_value=3) as mock_insert,
    ):
        await flight_search_service.search("DEL", "BOM", DEP)

    rows = {r["airline_code"]: r for r in mock_insert.call_args[0][0]}
    assert rows["6E"]["duration"] == "PT2H15M" and rows["6E"]["stops"] == 0
    assert rows["6E"]["arrival_time"] == f"{DEP}T08:25:00"
    assert rows["AI"]["duration"] == "PT4H5M" and rows["AI"]["stops"] == 1
    assert rows["QP"]["duration"] == "PT55M" and "stops" not in rows["QP"]
    assert "arrival_time" not in rows["QP"]


@pytest.mark.parametrize("bad", [-1, True, "1", 1.5])
@pytest.mark.asyncio
async def test_implausible_stop_values_are_dropped(bad):
    provider = {"status": STATUS_OK, "data": [
        {"price": 6200.0, "currency": "INR", "primary_airline": "6E",
         "departure_time": f"{DEP}T06:10:00", "stops": bad}]}
    with (
        patch("backend.services.flight_data_service.flight_data_service.search_flights",
              return_value=provider),
        patch("backend.services.historical_data_service.historical_data_service."
              "insert_observations", return_value=1) as mock_insert,
    ):
        await flight_search_service.search("DEL", "BOM", DEP)
    assert "stops" not in mock_insert.call_args[0][0][0]


# ── a column the table does not have yet must not cost the whole batch ──

def _row(**over):
    row = {"search_session_id": "33333333-3333-4333-8333-333333333333",
           "origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
           "departure_time": f"{DEP}T06:10:00", "departure_date": DEP,
           "cabin_class": "ECONOMY", "price": 6200.0, "currency": "INR",
           "is_live": True, "is_synthetic": False, "arrival_time": f"{DEP}T08:25:00"}
    row.update(over)
    return row


def test_missing_column_is_dropped_and_the_rows_are_kept(monkeypatch, caplog):
    attempts = []

    def execute_side_effect():
        submitted = table.insert.call_args[0][0]
        attempts.append(submitted)
        if any("arrival_time" in r for r in submitted):
            raise Exception("{'message': \"Could not find the 'arrival_time' column of "
                            "'price_history' in the schema cache\", 'code': 'PGRST204'}")
        return MagicMock(data=[{}] * len(submitted))

    table = MagicMock()
    table.insert.return_value.execute.side_effect = execute_side_effect
    from backend.database.database import database
    monkeypatch.setattr(database.supabase, "table", MagicMock(return_value=table))

    assert historical_data_service.insert_observations([_row()]) == 1
    assert len(attempts) == 2 and "arrival_time" not in attempts[-1][0]
    assert "no 'arrival_time' column" in caplog.text


def test_other_insert_errors_still_raise(monkeypatch):
    table = MagicMock()
    table.insert.return_value.execute.side_effect = Exception("connection reset")
    from backend.database.database import database
    monkeypatch.setattr(database.supabase, "table", MagicMock(return_value=table))
    with pytest.raises(Exception, match="connection reset"):
        historical_data_service.insert_observations([_row()])
