import pytest
import os
import sys
import json
import uuid
import math
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta

# Core imports
from backend.services.historical_data_service import historical_data_service
from backend.services.route_collection_strategy import route_collection_strategy
from backend.services.training_policy import TrainingPolicy
from backend.services.dataset_quality_validator import DatasetQualityValidator
from backend.services.training_dataset_builder import training_dataset_builder
from backend.services.forecast_store import forecast_store
from backend.services.forecast_evaluator import forecast_evaluator
from backend.services.forecast_evaluation_scheduler import ForecastEvaluationScheduler
from backend.services.booking_curve_definition import BOOKING_CURVE_KEYS, lag_tolerance_days
from backend.services.ingestion_controller import MarketDataController
from backend.services.flight_data_service import STATUS_OK, STATUS_EMPTY, STATUS_ERROR
from backend.services.scheduler import _collect_popular_routes_async
from backend.ml.price_model import PricePredictor

# ── 1. HISTORICAL DATA SERVICE ──────────────────────────────────────────

def test_historical_data_service(monkeypatch):
    """Verify HistoricalDataService appends observations and snapshot metadata.

    The persisted count must come from the database's response, not from
    `len(records)`. This test previously mocked `execute()` with a bare MagicMock
    — a response carrying no rows at all — and asserted a count of 1, which is
    the defect: the caller was told one row was persisted by a stub that never
    reported persisting anything.

    The record carries a `currency` and a fare inside the loaders' window because
    `insert_observations` screens the batch before submitting it (AUDIT-FIXES.md
    §48). A fixture missing either is refused at the writer, and this test's
    subject is the count it reports, not the screen.
    """
    mock_tbl_obj = MagicMock()
    mock_insert_obj = MagicMock()

    records = [{"origin_code": "DEL", "price": 5000.0, "currency": "INR"}]
    mock_tbl_obj.insert = MagicMock(return_value=mock_insert_obj)
    # PostgREST returns the created rows; that list is the count under test.
    mock_insert_obj.execute = MagicMock(return_value=MagicMock(data=list(records)))

    from backend.database.database import database
    monkeypatch.setattr(database.supabase, "table", MagicMock(return_value=mock_tbl_obj))

    # Ingest observations
    cnt = historical_data_service.insert_observations(records)
    assert cnt == 1
    database.supabase.table.assert_called_with("price_history")
    mock_tbl_obj.insert.assert_called_with(records)

    # Ingest snapshot metadata
    meta = {"snapshot_id": "snap-123", "search_success": True}
    historical_data_service.insert_snapshot_metadata(meta)
    database.supabase.table.assert_called_with("snapshot_metadata")
    mock_tbl_obj.insert.assert_called_with(meta)


def test_insert_observations_reports_what_the_db_confirmed(monkeypatch):
    """Three submitted, two acknowledged, must report two — not three.

    Storable rows on purpose: since AUDIT-FIXES.md §48 the writer screens the batch
    for currency and the fare window first, so `{"price": 1.0}` would never reach
    the insert and the count under test would always be 0.
    """
    mock_tbl_obj = MagicMock()
    mock_insert_obj = MagicMock()
    mock_tbl_obj.insert = MagicMock(return_value=mock_insert_obj)

    from backend.database.database import database
    monkeypatch.setattr(database.supabase, "table", MagicMock(return_value=mock_tbl_obj))

    records = [{"price": 5000.0, "currency": "INR"},
               {"price": 6000.0, "currency": "INR"},
               {"price": 7000.0, "currency": "INR"}]
    mock_insert_obj.execute = MagicMock(return_value=MagicMock(data=records[:2]))
    assert historical_data_service.insert_observations(records) == 2

    # An empty acknowledgement is a real answer: nothing was written.
    mock_insert_obj.execute = MagicMock(return_value=MagicMock(data=[]))
    assert historical_data_service.insert_observations(records) == 0

    # No representation at all is *not* an answer. -1 keeps "the database did
    # not say" from being read as a confirmed count of any size.
    class _NoData:
        pass

    mock_insert_obj.execute = MagicMock(return_value=_NoData())
    assert historical_data_service.insert_observations(records) == -1

    # Nothing submitted, nothing claimed.
    assert historical_data_service.insert_observations([]) == 0


def test_insert_observations_propagates_failure(monkeypatch):
    """A failed insert must raise, never return a count."""
    mock_tbl_obj = MagicMock()
    mock_insert_obj = MagicMock()
    mock_tbl_obj.insert = MagicMock(return_value=mock_insert_obj)
    mock_insert_obj.execute = MagicMock(side_effect=RuntimeError("column does not exist"))

    from backend.database.database import database
    monkeypatch.setattr(database.supabase, "table", MagicMock(return_value=mock_tbl_obj))

    with pytest.raises(RuntimeError, match="column does not exist"):
        historical_data_service.insert_observations([{"price": 5000.0, "currency": "INR"}])

# ── 2. ROUTE COLLECTION STRATEGY ────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_collection_strategy(monkeypatch):
    """Verify RouteCollectionStrategy fetches dynamically and removes duplicates."""
    mock_ph_data = [{"origin_code": "DEL", "destination_code": "BOM"}]
    mock_pa_data = [{"origin_code": "DEL", "destination_code": "BOM"}, {"origin_code": "CCU", "destination_code": "MAA"}]
    
    from backend.database.database import database
    
    def mock_table_select(table_name):
        mock_tbl = MagicMock()
        if table_name == "price_history":
            mock_limit = MagicMock()
            mock_limit.limit = MagicMock(return_value=mock_limit)
            mock_limit.execute = MagicMock(return_value=MagicMock(data=mock_ph_data))
            mock_tbl.select = MagicMock(return_value=mock_limit)
        elif table_name == "price_alerts":
            mock_eq = MagicMock()
            mock_eq.eq = MagicMock(return_value=mock_eq)
            mock_eq.execute = MagicMock(return_value=MagicMock(data=mock_pa_data))
            mock_tbl.select = MagicMock(return_value=mock_eq)
        return mock_tbl
        
    monkeypatch.setattr(database.supabase, "table", mock_table_select)
    
    routes = await route_collection_strategy.get_routes_to_collect()
    
    # Base routes + dynamic routes. Deduplicated
    assert ("DEL", "BOM") in routes
    assert ("CCU", "MAA") in routes
    assert len(routes) > 0
    # No duplicates allowed
    assert len(routes) == len(list(set(routes)))

# ── 3. SCHEDULER OUTCOME ACCOUNTING ───────────────────────────────────────
#
# Both tests in this section used to assert against outcomes the collector cannot
# produce. They built a `FlightSearchPresentation` with `flights=` and *no
# metadata*, so every search came back with `provider_status = None` — a value the
# real `flight_search_service.search` never returns (it coerces None to "error"
# before returning) and which the collector counts as a failed search. One test
# then matched the message "zero observations inserted", which stopped existing
# when the zero-rows gate learned to name which of the three failure modes
# happened; the other expected a clean six-horizon run out of six failed searches.
#
# The collector reads its entire outcome out of `metadata`, so the fixtures do too.


def _flight(price=5000.0):
    from backend.services.flight_presentation import NormalizedFlight
    return NormalizedFlight(
        id="F1", primary_airline="6E", primary_airline_name="IndiGo", flight_number="6E101",
        itineraries=[], price=price, currency="INR",
    )


def _presentation(status, *, flights=None, rows_submitted=0, rows_persisted=None,
                  persistence_error=None, unidentified_rows=0):
    """A presentation shaped like the one `flight_search_service.search` returns.

    `provider_status` says whether anything was scraped; `rows_submitted` and
    `rows_persisted` say whether it was stored. `rows_persisted=None` means no
    insert was attempted and -1 means it was attempted but unconfirmed — neither is
    a written row, and the collector must not count either as one.
    `unidentified_rows` is how many of the stored rows carry an incomplete
    booking-curve identity, which is to say how many of them can never be labelled.
    """
    from backend.services.flight_presentation import FlightSearchPresentation
    return FlightSearchPresentation(
        flights=list(flights or []),
        recommendation={"action": "WAIT", "reasoning": "Test", "trend": "STABLE"},
        metadata={
            "provider_status": status,
            "provider_error_kind": "timeout" if status == STATUS_ERROR else None,
            "rows_submitted": rows_submitted,
            "rows_persisted": rows_persisted,
            "persistence_error": persistence_error,
            "unidentified_rows": unidentified_rows,
        },
    )


def _one_route(monkeypatch, *, buckets=(7,)):
    """Point the collector at one route and `buckets`; return the snapshot-write spy.

    Retries are patched to not sleep. `retry_backoff_seconds` in routes.yaml is 30
    and the collector honours it, so any test that lets a search fail otherwise
    costs 30s per retry per search.
    """
    from backend.route_catalog import route_catalog_config
    monkeypatch.setattr(route_catalog_config, "create_route_batches",
                        MagicMock(return_value=[[("DEL", "BOM")]]))
    monkeypatch.setattr(route_catalog_config, "get_departure_buckets",
                        MagicMock(return_value=list(buckets)))
    monkeypatch.setattr(route_catalog_config, "get_retry_attempts", MagicMock(return_value=2))
    monkeypatch.setattr(route_catalog_config, "get_retry_backoff_seconds",
                        MagicMock(return_value=0))
    snapshot_spy = MagicMock()
    monkeypatch.setattr(historical_data_service, "insert_snapshot_metadata", snapshot_spy)
    return snapshot_spy

@pytest.mark.asyncio
async def test_collection_reports_rows_the_database_confirmed(monkeypatch):
    """A run that stored rows completes, and reports the confirmed count.

    `rows_inserted` used to be `+= len(pres.flights)` — the number of flights
    *displayed*, which for a route served from cache is a count of rows read back
    out of the database rather than written to it.
    """
    from backend.services.flight_search_service import flight_search_service
    snapshot_spy = _one_route(monkeypatch, buckets=(7, 14))
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(
        return_value=_presentation(STATUS_OK, flights=[_flight()],
                                   rows_submitted=3, rows_persisted=3)))

    await _collect_popular_routes_async()

    meta = snapshot_spy.call_args[0][0]
    assert meta["rows_inserted"] == 6, meta          # two searches, three confirmed rows each
    assert meta["rows_submitted"] == 6, meta
    assert meta["search_count"] == 2, meta
    assert meta["routes_live"] == 2, meta
    assert meta["routes_persistence_error"] == 0, meta
    assert meta["search_success"] is True, meta


@pytest.mark.asyncio
async def test_run_raises_when_the_provider_failed_on_every_search(monkeypatch):
    """Nothing was scraped: the gate must fire and say the provider was the reason."""
    from backend.services.flight_search_service import flight_search_service
    snapshot_spy = _one_route(monkeypatch, buckets=(7, 14))
    monkeypatch.setattr(flight_search_service, "search",
                        AsyncMock(return_value=_presentation(STATUS_ERROR)))

    with pytest.raises(RuntimeError) as excinfo:
        await _collect_popular_routes_async()

    msg = str(excinfo.value)
    assert "the provider failed on all 2 search(es)" in msg, msg
    # The three zero-row modes were one message ("zero observations inserted"), so
    # the reader could not tell a broken provider from a broken write. Asserting the
    # other two phrases are absent is what keeps them apart.
    assert "none were stored" not in msg, msg
    assert "reported no flights" not in msg, msg
    # A run that failed its own gate has no snapshot to record.
    snapshot_spy.assert_not_called()

@pytest.mark.asyncio
async def test_run_raises_when_every_route_came_back_empty(monkeypatch):
    """A parseable "no flights" on every search is a distinct failure from a broken one."""
    from backend.services.flight_search_service import flight_search_service
    _one_route(monkeypatch, buckets=(7, 14, 21))
    monkeypatch.setattr(flight_search_service, "search",
                        AsyncMock(return_value=_presentation(STATUS_EMPTY)))

    with pytest.raises(RuntimeError) as excinfo:
        await _collect_popular_routes_async()

    msg = str(excinfo.value)
    assert "reported no flights on any of 3 search(es)" in msg, msg
    assert "the provider failed" not in msg, msg


@pytest.mark.asyncio
async def test_run_raises_when_scraped_rows_were_not_stored(monkeypatch):
    """Scraped but not persisted is the mode the old counter could not see at all.

    The provider answered, flights came back, and the database confirmed none of
    them. Counting displayed flights made this look like a successful collection.
    """
    from backend.services.flight_search_service import flight_search_service
    _one_route(monkeypatch, buckets=(7,))
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(
        return_value=_presentation(STATUS_OK, flights=[_flight()],
                                   rows_submitted=4, rows_persisted=0)))

    with pytest.raises(RuntimeError) as excinfo:
        await _collect_popular_routes_async()

    msg = str(excinfo.value)
    assert "4 observation(s) were scraped" in msg, msg
    assert "none were stored" in msg, msg
    assert "the provider failed" not in msg, msg


@pytest.mark.asyncio
async def test_unconfirmed_write_is_not_counted_as_stored(monkeypatch):
    """`rows_persisted == -1` means the database did not say. It is not a row.

    -1 is what `insert_observations` returns when the insert was attempted and the
    response carried no representation of what was written. Added because
    `total_rows_persisted += rows_persisted` over -1 would silently *reduce* the
    total, and over any negative number the gate can be talked out of firing.
    """
    from backend.services.flight_search_service import flight_search_service
    _one_route(monkeypatch, buckets=(7,))
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(
        return_value=_presentation(
            STATUS_OK, flights=[_flight()], rows_submitted=2, rows_persisted=-1,
            persistence_error="database acknowledged no rows; persisted count unknown")))

    with pytest.raises(RuntimeError) as excinfo:
        await _collect_popular_routes_async()

    assert "none were stored" in str(excinfo.value), str(excinfo.value)


@pytest.mark.asyncio
async def test_run_storing_only_unidentifiable_rows_fails(monkeypatch):
    """Rows that can never be labelled are not a collection. The run goes red.

    Storing rows is not the collector's job; storing rows that can enter the label
    join is. `_price_at_offset` excludes an observation with an incomplete curve
    identity from that join on both sides, so a run whose every row lacks a
    `departure_time` grew `price_history` by nothing trainable — which means the
    provider stopped publishing departure times, not that the market went quiet.

    Before this gate that run passed the zero-rows check above it, logged "Stored 6
    observation(s)", wrote a snapshot recording `search_success: True`, and exited 0.
    The count it needed was already being computed, in
    `deduplicate_observation_batch`'s `unindexable` field, and thrown away by its
    only production caller.
    """
    from backend.services.flight_search_service import flight_search_service
    _one_route(monkeypatch, buckets=(7, 14))
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(
        return_value=_presentation(STATUS_OK, flights=[_flight()], rows_submitted=3,
                                   rows_persisted=3, unidentified_rows=3)))

    with pytest.raises(RuntimeError) as excinfo:
        await _collect_popular_routes_async()

    msg = str(excinfo.value)
    assert "incomplete booking-curve identity" in msg, msg
    # Names the keys rather than a count, so the reader knows which column is missing.
    for key in BOOKING_CURVE_KEYS:
        assert key in msg, msg
    # Not the zero-rows message: six rows *were* stored.
    assert "zero" not in msg.lower(), msg


@pytest.mark.asyncio
async def test_partially_unidentifiable_run_succeeds_and_records_both_counts(monkeypatch):
    """A run with some labellable rows passes, and says how many of each it stored.

    The two numbers are separate because they answer different questions: whether
    the table grew, and whether the training corpus did. A single "rows_inserted"
    figure cannot distinguish a healthy run from one quietly degrading toward the
    case above.
    """
    from backend.services.flight_search_service import flight_search_service
    snapshot_spy = _one_route(monkeypatch, buckets=(7, 14))
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(
        return_value=_presentation(STATUS_OK, flights=[_flight()], rows_submitted=5,
                                   rows_persisted=5, unidentified_rows=2)))

    await _collect_popular_routes_async()

    meta = snapshot_spy.call_args[0][0]
    assert meta["rows_inserted"] == 10, meta        # two searches, five confirmed rows each
    assert meta["rows_identity_known"] == 10, meta
    assert meta["rows_unidentified"] == 4, meta
    assert meta["rows_identified"] == 6, meta
    assert meta["rows_identified"] + meta["rows_unidentified"] == meta["rows_identity_known"], meta
    assert meta["search_success"] is True, meta


@pytest.mark.asyncio
async def test_partial_write_leaves_the_identity_split_unknown(monkeypatch):
    """A partial write is counted in neither identity bucket, while its siblings are.

    `unidentified_rows` is measured over the rows submitted and `rows_persisted` says
    how many landed; nothing says *which* landed. Attributing the shortfall either way
    invents a fact — and attributing it to the unidentified bucket would let the gate
    above fail a run that did store labellable rows. The persistence shortfall is
    already reported by `routes_persistence_error`, which owns that failure.

    Three clean searches run alongside the partial one, for two reasons. The weaker
    one is that a lone partial write is now a 100% search-failure rate and trips the
    yield gate below, which is correct behaviour and has its own test. The stronger
    one is that this shape actually proves *exclusion*: `rows_identity_known` is 15
    rather than 17, so the two rows that did land out of nine are demonstrably left
    out of the denominator. The single-search version could only show the counters
    sitting at zero, which is equally consistent with the accumulator never running.
    """
    from backend.services.flight_search_service import flight_search_service
    snapshot_spy = _one_route(monkeypatch, buckets=(7, 14, 21, 30))
    clean = _presentation(STATUS_OK, flights=[_flight()], rows_submitted=5,
                          rows_persisted=5, unidentified_rows=0)
    partial = _presentation(
        STATUS_OK, flights=[_flight()], rows_submitted=9, rows_persisted=2,
        unidentified_rows=5,
        persistence_error="submitted 9 observation(s), database persisted 2")
    monkeypatch.setattr(flight_search_service, "search",
                        AsyncMock(side_effect=[clean, clean, clean, partial]))

    await _collect_popular_routes_async()

    meta = snapshot_spy.call_args[0][0]
    # 5+5+5 confirmed, plus the 2 of 9 that landed on the partial write.
    assert meta["rows_inserted"] == 17, meta
    assert meta["rows_submitted"] == 24, meta
    # The partial batch's 2 rows are in `rows_inserted` and in neither identity bucket.
    assert meta["rows_identity_known"] == 15, meta
    assert meta["rows_unidentified"] == 0, meta
    assert meta["rows_identified"] == 15, meta
    assert meta["routes_persistence_error"] == 1, meta
    # The persistence shortfall is still reported as a failure of the run.
    assert meta["search_success"] is False, meta


@pytest.mark.asyncio
async def test_a_run_whose_only_search_partly_wrote_fails_the_yield_gate(monkeypatch):
    """A partial write counts as a failed search, so one-of-one partial is a red run.

    Pinned because it is a real semantic choice and not a rounding artefact. A search
    that submitted nine rows and stored two has a broken write path, `failed_searches`
    counts it, and over a single search that is a 100% failure rate. The alternative
    considered was a minimum-sample rule — do not judge a rate until N searches have
    run — which was rejected: it adds a knob that can be misconfigured, and in
    production the case it would suppress (a handful of searches, most of them failing)
    is precisely the case the gate exists to catch. On the real 715-search run this
    branch cannot be reached by a single bad write.
    """
    from backend.services.flight_search_service import flight_search_service
    snapshot_spy = _one_route(monkeypatch, buckets=(7,))
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(
        return_value=_presentation(
            STATUS_OK, flights=[_flight()], rows_submitted=9, rows_persisted=2,
            unidentified_rows=5,
            persistence_error="submitted 9 observation(s), database persisted 2")))

    with pytest.raises(RuntimeError) as excinfo:
        await _collect_popular_routes_async()

    msg = str(excinfo.value)
    assert "1 of 1 search(es) failed" in msg, msg
    assert "1 persistence" in msg, msg
    # Not one of the zero-row gates: two rows did land.
    assert "none were stored" not in msg, msg
    snapshot_spy.assert_not_called()


def _no_retries(monkeypatch):
    """One provider call per search, so a `side_effect` list maps 1:1 onto searches.

    `_one_route` sets two attempts, which is right for the retry tests but means a
    failing search consumes two entries from a `side_effect` sequence.
    """
    from backend.route_catalog import route_catalog_config
    monkeypatch.setattr(route_catalog_config, "get_retry_attempts", MagicMock(return_value=1))


@pytest.mark.asyncio
async def test_run_with_a_token_yield_fails_even_though_rows_were_stored(monkeypatch):
    """One live search out of five is not a collected day, and used to exit 0.

    This is the hole the other two gates leave open. Rows were stored, so the
    zero-rows gate is silent; they carry a complete identity, so the identity gate is
    silent; and the incompleteness was only logged. A broken selector or an expired
    session looks exactly like this.
    """
    from backend.services.flight_search_service import flight_search_service
    snapshot_spy = _one_route(monkeypatch, buckets=(3, 7, 14, 21, 30))
    _no_retries(monkeypatch)
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(side_effect=[
        _presentation(STATUS_OK, flights=[_flight()], rows_submitted=3, rows_persisted=3),
        _presentation(STATUS_ERROR), _presentation(STATUS_ERROR),
        _presentation(STATUS_ERROR), _presentation(STATUS_ERROR),
    ]))

    with pytest.raises(RuntimeError) as excinfo:
        await _collect_popular_routes_async()

    msg = str(excinfo.value)
    assert "4 of 5 search(es) failed" in msg, msg
    assert "80.0%" in msg, msg
    assert "50% ceiling" in msg, msg
    # Rows *did* store, so this must not be reported as either zero-row mode.
    assert "none were stored" not in msg, msg
    assert "the provider failed on all" not in msg, msg
    snapshot_spy.assert_not_called()


@pytest.mark.asyncio
async def test_failure_rate_below_the_ceiling_completes_and_is_recorded(monkeypatch):
    """One failure in four is ordinary scraper flakiness, not a failed run.

    The gate is a ceiling, not a demand for perfection — but the rate it measured is
    written to the snapshot beside the ceiling it was measured against, because an
    environment variable read at run time is not recoverable from the row later.
    """
    from backend.services.flight_search_service import flight_search_service
    snapshot_spy = _one_route(monkeypatch, buckets=(3, 7, 14, 21))
    _no_retries(monkeypatch)
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(side_effect=[
        _presentation(STATUS_OK, flights=[_flight()], rows_submitted=2, rows_persisted=2),
        _presentation(STATUS_OK, flights=[_flight()], rows_submitted=2, rows_persisted=2),
        _presentation(STATUS_OK, flights=[_flight()], rows_submitted=2, rows_persisted=2),
        _presentation(STATUS_ERROR),
    ]))

    await _collect_popular_routes_async()

    meta = snapshot_spy.call_args[0][0]
    assert meta["search_count"] == 4, meta
    assert meta["routes_provider_error"] == 1, meta
    assert meta["search_failure_rate"] == 0.25, meta
    assert meta["search_failure_rate_ceiling"] == 0.5, meta
    assert meta["rows_inserted"] == 6, meta
    # Below the ceiling is not the same as clean: a failed search still costs the run
    # its `search_success`, which is what the existing flag has always meant.
    assert meta["search_success"] is False, meta


@pytest.mark.asyncio
async def test_the_ceiling_is_configurable_and_the_gate_reads_it(monkeypatch):
    """Same run as above, tighter ceiling, and now it fails.

    Without this the gate could be a constant that happens to match the default, and
    `SCHEDULER_MAX_SEARCH_FAILURE_RATE` would be documentation rather than a control.
    """
    from backend.services.flight_search_service import flight_search_service
    _one_route(monkeypatch, buckets=(3, 7, 14, 21))
    _no_retries(monkeypatch)
    monkeypatch.setenv("SCHEDULER_MAX_SEARCH_FAILURE_RATE", "0.2")
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(side_effect=[
        _presentation(STATUS_OK, flights=[_flight()], rows_submitted=2, rows_persisted=2),
        _presentation(STATUS_OK, flights=[_flight()], rows_submitted=2, rows_persisted=2),
        _presentation(STATUS_OK, flights=[_flight()], rows_submitted=2, rows_persisted=2),
        _presentation(STATUS_ERROR),
    ]))

    with pytest.raises(RuntimeError) as excinfo:
        await _collect_popular_routes_async()

    msg = str(excinfo.value)
    assert "1 of 4 search(es) failed" in msg, msg
    assert "20% ceiling" in msg, msg


@pytest.mark.asyncio
async def test_a_quiet_market_is_not_counted_as_failure(monkeypatch):
    """STATUS_EMPTY is an answer, so a mostly-quiet day must not trip the yield gate.

    This is the whole reason the gate measures failures over searches rather than live
    over searches: the latter would turn a low-season route list red. A run that is
    empty *all* the way through stores nothing and is caught by the zero-rows gate
    instead, which `test_run_raises_when_every_route_came_back_empty` pins.
    """
    from backend.services.flight_search_service import flight_search_service
    snapshot_spy = _one_route(monkeypatch, buckets=(3, 7, 14, 21, 30))
    _no_retries(monkeypatch)
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(side_effect=[
        _presentation(STATUS_OK, flights=[_flight()], rows_submitted=2, rows_persisted=2),
        _presentation(STATUS_EMPTY), _presentation(STATUS_EMPTY),
        _presentation(STATUS_EMPTY), _presentation(STATUS_EMPTY),
    ]))

    await _collect_popular_routes_async()

    meta = snapshot_spy.call_args[0][0]
    assert meta["routes_empty"] == 4, meta
    assert meta["routes_live"] == 1, meta
    assert meta["search_failure_rate"] == 0.0, meta
    # No failures at all, so this run is a success by the flag's own definition.
    assert meta["search_success"] is True, meta

# ── 4. BOOKING CURVE COLLECTION HORIZONS ──────────────────────────────────

@pytest.mark.asyncio
async def test_booking_curve_collection_horizons(monkeypatch):
    """Every configured departure bucket is searched, once, on the right date."""
    from backend.services.flight_search_service import flight_search_service
    buckets = [7, 14, 21, 30, 45, 60]
    _one_route(monkeypatch, buckets=buckets)

    search_args = []

    async def spy_search(*args, **kwargs):
        search_args.append(kwargs)
        return _presentation(STATUS_OK, flights=[_flight()],
                             rows_submitted=1, rows_persisted=1)

    monkeypatch.setattr(flight_search_service, "search", spy_search)

    await _collect_popular_routes_async()

    assert len(search_args) == len(buckets), search_args
    horizons_called = [kwargs["departure_date"] for kwargs in search_args]
    today = datetime.now(timezone.utc)
    expected_dates = [(today + timedelta(days=h)).strftime("%Y-%m-%d") for h in buckets]
    assert sorted(horizons_called) == sorted(expected_dates)
    # Same route on every search: the buckets vary the date, not the pair.
    assert {(kw["origin_iata"], kw["destination_iata"]) for kw in search_args} == {("DEL", "BOM")}

# ── 5. TRAINING DATASET BUILDER ──────────────────────────────────────────

def test_training_dataset_builder_joins(monkeypatch):
    """Verify TrainingDatasetBuilder parses, removes duplicates, validates chronology, and aligns shifts."""
    # `provenance` is spread into every row below. This frame stands in for
    # `get_training_dataset`, whose predicate is `is_synthetic IS FALSE AND
    # is_live IS TRUE`, so a row it returns always carries both columns. The
    # rows here carried neither, and the builder's eligibility filter used to
    # let that pass — which is how the missing `is_live` condition in
    # `training_eligibility` went unnoticed.
    provenance = {"is_synthetic": False, "is_live": True}
    # The curve identity, shared by all four rows because they are four observations
    # of one flight. `departure_time` is the per-flight component of
    # `BOOKING_CURVE_KEYS` as of 2026-09-03; `flight_number` was, and it stays on the
    # rows because it is a real column of `price_history`, but nothing keys on it now.
    # Hand-copied across four literals this was four places to miss: without a
    # departure time the frame describes no curve at all, `attach_future_target`
    # refuses it, and the shifted-join assertion below is never reached.
    curve = {
        "origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI",
        "departure_date": "2026-07-26", "departure_time": "2026-07-26T06:10:00",
        "flight_number": "AI101",
    }
    raw_rows = [
        {**curve, "recorded_at": "2026-07-19T12:00:00", "price": 6000.0, **provenance},
        # Duplicate row with higher price (should be removed)
        {**curve, "recorded_at": "2026-07-19T12:00:00", "price": 7000.0, **provenance},
        # Chronology failure: booking date > departure date (should be filtered out)
        {**curve, "recorded_at": "2026-07-27T12:00:00", "price": 8000.0, **provenance},
        # Future target record (T + 1 day)
        {**curve, "recorded_at": "2026-07-20T12:00:00", "price": 6200.0, **provenance},
    ]
    
    from backend.database.database import database
    monkeypatch.setattr(database, "get_training_dataset", MagicMock(return_value=pd.DataFrame(raw_rows)))
    
    df_raw, df_shifted = training_dataset_builder.build(horizon=1)
    
    # 1 duplicate removed + 1 chronological failure removed = 2 valid raw rows left
    assert len(df_raw) == 2
    # 1 shifted join should align T (July 19) with target T+1 (July 20) -> Target: 6200.0
    assert len(df_shifted) == 1
    assert df_shifted.iloc[0]["target_price"] == 6200.0

# ── 6. DATASET QUALITY VALIDATOR & TRAINING POLICY ───────────────────────

def test_dataset_quality_validator_policy():
    """Verify DatasetQualityValidator checks policy thresholds and flags reports."""
    df_raw = pd.DataFrame([
        {"origin_code": "DEL", "destination_code": "BOM", "recorded_at": "2026-07-19T12:00:00", "departure_date": "2026-07-26"}
    ])
    df_shifted = pd.DataFrame([{"target_price": 5000.0}])
    
    policy = TrainingPolicy(min_shifted_rows=10, min_booking_curve_length=1)
    validator = DatasetQualityValidator(policy=policy)
    
    report = validator.validate(df_raw, df_shifted)
    
    assert report.observation_count == 1
    assert report.shifted_rows == 1
    # Policy requires 10 shifted rows, so it should fail
    assert report.passed is False

# ── 7. FORECAST STORE ────────────────────────────────────────────────────

def test_forecast_store_persistence(monkeypatch):
    """Verify ForecastStore saves immutable forecasts and defaults status to PENDING."""
    mock_tbl_obj = MagicMock()
    mock_insert_obj = MagicMock()
    
    mock_tbl_obj.insert = MagicMock(return_value=mock_insert_obj)
    mock_insert_obj.execute = MagicMock()
    
    from backend.database.database import database
    monkeypatch.setattr(database.supabase, "table", MagicMock(return_value=mock_tbl_obj))
    
    rec_payload = {"decision": "BOOK_NOW", "origin": "DEL", "destination": "BOM"}
    forecast_store.save_forecast(
        forecast_id="fc-123",
        prediction_timestamp="2026-07-19T12:00:00",
        horizon=3,
        predicted_price=5500.0,
        model_version="2.0.0",
        dataset_version="DS-1",
        recommendation=rec_payload
    )
    
    database.supabase.table.assert_called_with("forecast_store")
    payload = mock_tbl_obj.insert.call_args[0][0]
    assert payload["forecast_id"] == "fc-123"
    assert payload["status"] == "PENDING"
    assert payload["forecast_price"] == 5500.0

# ── 8. FORECAST EVALUATION SCHEDULER & EVALUATOR ──────────────────────────

class _FakePostgrest:
    """A PostgREST-shaped builder that accepts every link and records its filters.

    The mocks this replaces wired one exact chain — `table().select().eq().execute()`
    and `table().eq().execute()` — which was the shape `_load_pending` had *before* it
    was repaired. The repaired query is
    `.select("*").eq(...).order(...).limit(...).execute()`, so `.order` fell through to
    an auto-created `MagicMock`, `.data` was a `MagicMock` rather than the fixture rows,
    and `for forecast in pending` iterated a `MagicMock`'s default empty iterator. The
    run therefore read none of the rows below and returned 0 while asserting 1.

    Every method here returns `self`, so the fake does not encode a chain shape at all
    and cannot go stale the next time production adds a link. What it *does* record is
    the thing worth asserting on: which columns were filtered, and to what.
    """

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.filters = {}
        self.updates = []

    def select(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self
    def gte(self, *_a, **_k): return self
    def lte(self, *_a, **_k): return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def is_(self, column, value):
        self.filters[column] = value
        return self

    def update(self, patch):
        self.updates.append(dict(patch))
        return self

    def execute(self):
        return MagicMock(data=list(self.rows))


@pytest.mark.asyncio
async def test_forecast_evaluation_scheduler():
    """A pending forecast is scored against the fare its own curve realised.

    Three properties, each of which was a separate defect in this module:

    * the outcome is the **earliest** observation in the window, not the cheapest
      fare nearby — so the two decoy rows below, both cheaper than the answer, must
      not be selected;
    * the window is applied to `search_timestamp` where present, which is why the
      realised row's `recorded_at` deliberately sits *outside* the window while its
      search time sits inside it — the nightly-batch shape of the real corpus;
    * all five `BOOKING_CURVE_KEYS` are `.eq`-filtered, so the fare comes from the
      flight the forecast was about rather than from any of the carrier's other
      departures that day.
    """
    mock_forecasts = [{
        "id": "row-123",
        "forecast_id": "fc-123",
        "forecast_timestamp": "2026-07-19T12:00:00Z",
        "prediction_horizon": 1,
        "forecast_price": 5500.0,
        "status": "PENDING",
        # A complete booking-curve identity. `_curve_from` refuses a partial key
        # rather than pooling a carrier's departures, so a recommendation naming only
        # origin, destination and airline — which is what this fixture used to carry —
        # is retired UNEVALUABLE and never reaches the outcome query. The per-flight
        # component is `departure_time` as of 2026-09-03; it was `flight_number`, which
        # the provider does not publish, so *every* forecast stored before that date is
        # refused here. `test_a_forecast_without_a_departure_time_is_retired` below is
        # that path.
        "recommendation": {
            "origin": "DEL", "destination": "BOM", "airline": "6E",
            "departure_date": "2026-07-26",
            "departure_time": "2026-07-26T06:10:00",
        },
    }]

    # Horizon 1 puts the label at 2026-07-20T12:00Z with a 0.5-day tolerance, so the
    # accepted window is [07-20T12:00, 07-21T00:00] and rows are *fetched* over
    # [07-20T00:00, 07-21T12:00] — widened by the tolerance on both sides.
    assert lag_tolerance_days(1) == 0.5
    mock_history = [
        # Cheapest row in the fetch range, but observed six hours before the horizon
        # elapsed. This is the row a `min()` over the fetched rows returns.
        {"price": 4000.0, "search_timestamp": "2026-07-20T06:00:00+00:00",
         "recorded_at": "2026-07-20T23:45:00+00:00"},
        # The realised fare. Its `recorded_at` is the nightly batch write on the 21st,
        # outside the window; its `search_timestamp` is inside. A window applied to
        # `recorded_at` would miss this row and report no outcome.
        {"price": 5000.0, "search_timestamp": "2026-07-20T12:00:00+00:00",
         "recorded_at": "2026-07-21T06:00:00+00:00"},
        # Inside the window, later, and cheaper: the row a `min()` restricted to the
        # window returns.
        {"price": 4500.0, "search_timestamp": "2026-07-20T20:00:00+00:00",
         "recorded_at": "2026-07-21T06:00:00+00:00"},
    ]
    
    forecasts_table = _FakePostgrest(mock_forecasts)
    history_table = _FakePostgrest(mock_history)
    fake_db = MagicMock()
    # Injected rather than monkeypatched onto the module singleton: `__init__` takes a
    # database for exactly this, and the singleton's client is shared with every other
    # test in this file.
    fake_db.supabase.table = lambda name: {
        "forecast_store": forecasts_table,
        "price_history": history_table,
    }[name]

    completed = await ForecastEvaluationScheduler(
        database=fake_db).evaluate_pending_forecasts()
    assert completed == 1

    # The outcome query asked about one flight, by all five components of the curve.
    for key in BOOKING_CURVE_KEYS:
        assert key in history_table.filters, (
            f"the outcome query did not filter on {key}; without it the realised fare "
            f"can come from another of the carrier's departures")
    assert history_table.filters["airline_code"] == "6E"
    assert history_table.filters["departure_time"] == "2026-07-26T06:10:00"

    # And what it wrote back is the measured error of that fare, with its provenance.
    assert len(forecasts_table.updates) == 1
    patch = forecasts_table.updates[0]
    assert patch["status"] == "COMPLETED"
    assert patch["actual_price"] == 5000.0, (
        f"expected the earliest in-window observation (5000.0); got "
        f"{patch['actual_price']} — 4000.0 is the cheapest fetched row and 4500.0 the "
        f"cheapest inside the window, and neither is a realised price of anything")
    metrics = patch["evaluation_metrics"]
    assert metrics["error"] == 500.0          # signed: the forecast was ₹500 high
    assert metrics["abs_error"] == 500.0
    assert metrics["percentage_error"] == 10.0
    assert metrics["target_time"] == "2026-07-20T12:00:00+00:00"
    assert metrics["window_end"] == "2026-07-21T00:00:00+00:00"
    assert metrics["observed_at"] == "2026-07-20T12:00:00+00:00"
    
    # Assert evaluator computes correctly.
    #
    # The frame carried a `recommendation` column, which nothing reads: it fed
    # `recommendation_accuracy`, removed from the evaluator because it scored
    # `MONITOR` as automatically correct and needs the fare quoted at the time of
    # the advice, which no column here carries.
    #
    # `bias` was renamed `mean_error`, the name `backend.ml.metrics` gives that
    # quantity, so the project has one name for it. The evaluator used to publish
    # it twice — as `bias` (mean of the errors) and as `drift` (difference of the
    # means), which are the same number.
    df_eval = pd.DataFrame([{
        "forecast_price": 5500.0,
        "actual_price": 5000.0,
    }])
    report = forecast_evaluator.evaluate(df_eval)
    assert report["mae"] == 500.0
    assert report["mape"] == 10.0          # 500 / 5000, not 500 / max(5000, 1)
    assert report["mean_error"] == 500.0   # signed: the forecast was ₹500 high
    assert report["sample_count"] == 1
    assert report["excluded_rows"] == 0


@pytest.mark.asyncio
async def test_a_forecast_without_a_departure_time_is_retired_not_pooled():
    """An unidentifiable forecast is taken out of the queue, not matched loosely.

    This is the state of every forecast stored before 2026-09-03: the per-flight curve
    component was `flight_number`, the provider publishes none, so the recommendation
    names no flight and no departure time. Matching such a row on the four components
    it *does* name would pool every 6E departure on DEL-BOM that day and call one of
    their fares this forecast's outcome.

    Two things must hold. The outcome query is never issued at all — a partial key
    must not reach it — and the row does not stay PENDING, which is what `continue`
    used to do and is why the queue could only grow.
    """
    forecasts_table = _FakePostgrest([{
        "id": "row-124",
        "forecast_id": "fc-124",
        "forecast_timestamp": "2026-07-19T12:00:00Z",
        "prediction_horizon": 1,
        "forecast_price": 5500.0,
        "status": "PENDING",
        "recommendation": {"origin": "DEL", "destination": "BOM", "airline": "6E"},
    }])
    history_table = _FakePostgrest([{"price": 5000.0,
                                     "search_timestamp": "2026-07-20T12:00:00+00:00"}])
    fake_db = MagicMock()
    fake_db.supabase.table = lambda name: {
        "forecast_store": forecasts_table,
        "price_history": history_table,
    }[name]

    completed = await ForecastEvaluationScheduler(
        database=fake_db).evaluate_pending_forecasts()
    assert completed == 0
    assert history_table.filters == {}, (
        "the outcome query ran on an incomplete curve key: "
        f"{history_table.filters}")

    patch = forecasts_table.updates[0]
    assert patch["status"] == "UNEVALUABLE"
    assert "actual_price" not in patch, (
        "an unevaluable forecast was given a fare; there is no measured outcome to "
        "record and a placeholder is how a fabricated error figure gets into the table")
    reason = patch["evaluation_metrics"]["unevaluable_reason"]
    assert "departure_time" in reason and "departure_date" in reason, reason

# ── 9. MODEL METADATA AND SKIP POLICY ────────────────────────────────────

def test_model_metadata_and_skip_policy(tmp_path, monkeypatch):
    """Verify weights and json metadata are split, and training skips on policy failure."""
    predictor = PricePredictor()
    
    # Set BASE_ML_DIR to tmp_path to prevent overwriting prod models
    monkeypatch.setattr(sys.modules["backend.ml.price_model"], "BASE_ML_DIR", str(tmp_path))
    monkeypatch.setattr(sys.modules["backend.ml.price_model"], "MODEL_PATH", os.path.join(str(tmp_path), "global_model.pkl"))
    
    # Mock TrainingDatasetBuilder & DatasetQualityValidator to fail validation
    mock_df = pd.DataFrame([{"origin_code": "DEL", "destination_code": "BOM", "price": 5000.0}])
    monkeypatch.setattr(training_dataset_builder, "build", MagicMock(return_value=(mock_df, pd.DataFrame())))
    
    # Validation failed -> passed is False
    from backend.services.dataset_quality_validator import DatasetQualityReport
    mock_report = DatasetQualityReport(
        observation_count=1, shifted_rows=0, duplicate_rate=0.0, missing_rate=0.0,
        route_coverage=1, departure_coverage=1, booking_curve_length=1,
        temporal_coverage_days=1, passed=False
    )
    monkeypatch.setattr(DatasetQualityValidator, "validate", MagicMock(return_value=mock_report))
    
    predictor.train()
    
    # No pkl files should be saved because skip policy was triggered
    path_pkl = os.path.join(str(tmp_path), "models", "fare_forecast_3d.pkl")
    assert not os.path.exists(path_pkl)

# ── 10. NO SYNTHETIC VALUES ──────────────────────────────────────────────

def test_no_synthetic_values():
    """Verify no synthetic features are fabricated (e.g. seats default to NULL/None)."""
    payload = MarketDataController.format_payload(
        origin_code="DEL",
        destination_code="BOM",
        airline_code="AI",
        price=5000.0,
        departure_date="2026-07-26",
        days_until_dep=7,
        seats_available=None # Explicitly missing
    )
    
    # Unknown seats should remain None (SQL NULL), never fabricated to 9 or 30
    assert payload["seats_available"] is None
    assert payload["demand_score"] is None
    assert payload["seasonality_factor"] is None

    # And an unstated currency must stay None, never the literal "INR". The
    # parameter defaulted to "INR" until AUDIT-FIXES.md §48 while the one
    # production caller never passed it, so every row this function produced
    # claimed rupees whatever the provider had quoted — the 156 stored rows at
    # ₹58–₹105 on 2026-07-19 are US dollars.
    assert payload["currency"] is None
    assert "currency" not in MarketDataController.get_db_payload(payload)
