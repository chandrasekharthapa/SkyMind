"""Write-side observation de-duplication.

Migration 001 STEP 8b creates `ux_price_history_observation`, a unique index on
one observation per flight per search session. PostgREST submits a batch insert as
a single statement, so from the moment that index exists one duplicated provider
card rejects the entire route's batch. STEP 8's PRECONDITION names writer-side
de-duplication as the gate on running 8b; `deduplicate_observation_batch` is that
de-duplication, and these are its tests.

Two of them are the reason the rest exist. `test_separate_searches_are_never_collapsed`
guards the only thing this function could destroy — the longitudinal signal, which
is the whole corpus. And `test_key_matches_the_migrations_index` reads the index's
column list out of the SQL file and compares it with the tuple the code uses, because
a de-duplication key that disagrees with the index it is protecting against protects
against nothing, and this project has already shipped three copies of a join that
disagreed.
"""

import re
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

from backend.services.booking_curve_definition import (
    BOOKING_CURVE_KEYS,
    OBSERVATION_IDENTITY_KEYS,
    deduplicate_observation_batch,
    observation_identity_key,
)
from backend.services.flight_data_service import STATUS_OK
from backend.services.flight_search_service import flight_search_service
from backend.services.historical_data_service import historical_data_service

SESSION = "11111111-1111-4111-8111-111111111111"


def _row(**over):
    """A `get_db_payload`-shaped row: every column the index reads, plus a price.

    Mirrors what `MarketDataController.get_db_payload` produces, including its habit
    of dropping keys whose value is None — passing `departure_time=None` here removes
    the key rather than setting it, because that is what the writer actually submits.

    `currency` is here because `insert_observations` screens a batch before it
    collapses it (AUDIT-FIXES.md §48): a row that does not say what its fare is
    denominated in is refused at the writer, so a fixture without it would be
    testing the screen instead of the de-duplicator.
    """
    row = {
        "search_session_id": SESSION,
        "origin_code": "DEL",
        "destination_code": "BOM",
        "airline_code": "6E",
        "departure_time": "2026-07-20T06:10:00",
        "departure_date": "2026-07-20",
        "cabin_class": "ECONOMY",
        "price": 6200.0,
        "currency": "INR",
        "is_live": True,
        "is_synthetic": False,
    }
    row.update(over)
    return {k: v for k, v in row.items() if v is not None}


# ── what must be collapsed ────────────────────────────────────────────────────

def test_repeated_provider_card_collapses_to_one():
    kept, report = deduplicate_observation_batch([_row(), _row()])
    assert len(kept) == 1
    assert report["submitted"] == 2
    assert report["kept"] == 1
    assert report["dropped"] == 1
    assert report["groups_collapsed"] == 1
    # Same price twice is a repeated card, not two fares for one flight.
    assert report["groups_disagreeing_on_price"] == 0
    assert report["max_price_spread"] == 0.0


def test_cheapest_survives_regardless_of_provider_ordering():
    """The determinism claim in the docstring, tested in both orders.

    Provider ordering varies between runs. If the survivor depended on it, two
    identical scrapes of the same flight would store different fares, and the
    corpus would carry the scraper's ordering as if it were market data.
    """
    cheap, dear = _row(price=5900.0), _row(price=6200.0)

    kept, _ = deduplicate_observation_batch([dear, cheap])
    assert [r["price"] for r in kept] == [5900.0]

    kept, _ = deduplicate_observation_batch([cheap, dear])
    assert [r["price"] for r in kept] == [5900.0]


def test_price_disagreement_is_reported_with_its_spread():
    """One flight listed at two fares is a fact worth surfacing, not just filtering."""
    _, report = deduplicate_observation_batch(
        [_row(price=6200.0), _row(price=5900.0), _row(price=6500.0)]
    )
    assert report["dropped"] == 2
    assert report["groups_collapsed"] == 1
    assert report["groups_disagreeing_on_price"] == 1
    assert report["max_price_spread"] == pytest.approx(600.0)


def test_ties_keep_the_earlier_row():
    first, second = _row(price=6200.0), _row(price=6200.0, seats_available=4)
    kept, _ = deduplicate_observation_batch([first, second])
    assert kept == [first]


def test_unreadable_price_loses_to_a_readable_one():
    """A row whose fare cannot be parsed must not win the comparison.

    `_observation_price` returns +inf for it. Were it 0.0 the unusable row would
    survive every group it appeared in and silently replace a real fare.
    """
    good = _row(price=6200.0)
    for bad_price in ("not-a-number", float("nan")):
        kept, _ = deduplicate_observation_batch([_row(price=bad_price), good])
        assert [r["price"] for r in kept] == [6200.0], bad_price
    # And with no readable fare anywhere, the first row still survives — the batch
    # is not silently emptied.
    kept, _ = deduplicate_observation_batch([_row(price="x"), _row(price="y")])
    assert len(kept) == 1


# ── what must NEVER be collapsed ──────────────────────────────────────────────

def test_separate_searches_are_never_collapsed():
    """The load-bearing test: two visits to the same flight are the training signal.

    `search_session_id` is in the key for exactly this reason. Drop it and this
    function would collapse a booking curve into a single point, which is not
    de-duplication but the destruction of the only thing the corpus is collected
    for — and it would do it silently, because the rows look identical apart from
    the fare and the timestamps.
    """
    later = _row(search_session_id="22222222-2222-4222-8222-222222222222", price=6600.0)
    kept, report = deduplicate_observation_batch([_row(), later])
    assert len(kept) == 2
    assert report["dropped"] == 0
    assert report["groups_collapsed"] == 0


def test_sibling_departures_are_not_collapsed():
    """Same carrier, route, date and search; different departure instant.

    This is the post-2026-09-03 curve identity doing its job. Under the old
    `flight_number` key — which the corpus proved to be a search-result rank — these
    two would have shared an identity and one would have been discarded.
    """
    kept, _ = deduplicate_observation_batch(
        [_row(departure_time="2026-07-20T06:10:00"),
         _row(departure_time="2026-07-20T19:45:00", price=5100.0)]
    )
    assert len(kept) == 2


@pytest.mark.parametrize("column", ["origin_code", "destination_code", "airline_code",
                                    "departure_date"])
def test_every_curve_component_separates(column):
    """No component of the identity may be ignored — one at a time, all of them."""
    kept, _ = deduplicate_observation_batch([_row(), _row(**{column: "ZZZ"})])
    assert len(kept) == 2, f"{column} did not separate two observations"


def test_cabin_class_separates_and_absent_cabin_matches_the_empty_string():
    """The index reads `COALESCE(cabin_class, '')`; this key must agree with it."""
    kept, _ = deduplicate_observation_batch(
        [_row(cabin_class="ECONOMY"), _row(cabin_class="BUSINESS", price=19000.0)]
    )
    assert len(kept) == 2

    # NULL and NULL collide in the index, so they must collide here too.
    kept, report = deduplicate_observation_batch(
        [_row(cabin_class=None), _row(cabin_class=None)]
    )
    assert len(kept) == 1 and report["dropped"] == 1

    # NULL and a value do not.
    kept, _ = deduplicate_observation_batch([_row(cabin_class=None), _row()])
    assert len(kept) == 2


def test_rows_the_index_does_not_cover_pass_through():
    """Outside 8b's partial predicate the database cannot reject them, so neither may we.

    Deciding two such rows are the same observation would be a judgement the index
    declines to make. They are counted instead, and `unindexable` is a useful number
    in its own right: a row with no `departure_time` is a row that can never carry a
    label.
    """
    no_time = [_row(departure_time=None), _row(departure_time=None)]
    kept, report = deduplicate_observation_batch(no_time)
    assert len(kept) == 2
    assert report["dropped"] == 0
    assert report["unindexable"] == 2

    no_session = [_row(search_session_id=None), _row(search_session_id=None)]
    kept, report = deduplicate_observation_batch(no_session)
    assert len(kept) == 2
    assert report["unindexable"] == 2

    assert observation_identity_key(_row(departure_time=None)) is None
    assert observation_identity_key(_row(search_session_id=None)) is None
    assert observation_identity_key(_row(departure_time="   ")) is None
    assert observation_identity_key(_row()) is not None


# ── the key and the index it protects must not drift apart ────────────────────

_MIGRATION = (Path(__file__).resolve().parents[1]
              / "database" / "migrations" / "001_price_history_and_run_metadata.sql")
_INDEX_STMT = "CREATE UNIQUE INDEX IF NOT EXISTS ux_price_history_observation"


def _index_columns_from_sql(sql: str):
    """`ux_price_history_observation`'s columns, in order, with COALESCE unwrapped.

    Anchored on the whole statement rather than on `CREATE UNIQUE INDEX`, which also
    appears in a comment about locking further up the file — the sort of near-miss
    that makes a parser read the wrong text and still pass.
    """
    start = sql.index(_INDEX_STMT)
    open_paren = sql.index("(", sql.index("public.price_history", start))
    depth = 0
    for i in range(open_paren, len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    else:
        raise AssertionError("unbalanced parentheses in the index definition")

    items, depth, current = [], 0, ""
    for ch in sql[open_paren + 1:end]:
        if ch == "," and depth == 0:
            items.append(current)
            current = ""
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        current += ch
    items.append(current)

    columns = []
    for item in items:
        text = " ".join(item.split())
        wrapped = re.match(r"(?i)coalesce\(\s*([a-z_]+)", text)
        columns.append(wrapped.group(1) if wrapped else text)
    return columns


def test_key_matches_the_migrations_index():
    """The Python key and the SQL index must name the same columns in the same order.

    Read out of the migration rather than restated here. A de-duplication key that
    is finer than its index lets a collision through and the batch is still
    rejected; one that is coarser discards a row the database would have accepted.
    Either way the check that reports "0 colliding groups" keeps saying so while the
    insert fails. This repo has already shipped three copies of a join that
    disagreed, so the agreement is asserted rather than assumed.
    """
    sql = _MIGRATION.read_text(encoding="utf-8")
    assert sql.count(_INDEX_STMT) == 1
    assert list(OBSERVATION_IDENTITY_KEYS) == _index_columns_from_sql(sql)


def test_index_predicate_names_exactly_what_makes_a_row_unindexable():
    """`observation_identity_key` returns None on two columns; 8b must gate on those two."""
    sql = _MIGRATION.read_text(encoding="utf-8")
    predicate = sql[sql.index("WHERE", sql.index(_INDEX_STMT)):]
    predicate = predicate[:predicate.index(";")]
    guarded = re.findall(r"(?i)([a-z_]+)\s+IS\s+NOT\s+NULL", predicate)
    assert sorted(guarded) == ["departure_time", "search_session_id"]


def test_key_is_derived_from_the_curve_definition():
    """Not hand-typed, and specifically not still naming `flight_number`.

    `flight_number` was the per-flight component until 2026-09-03, when the corpus
    showed it to be a search-result rank: 1,562 of 1,648 searches carried dense
    non-repeating suffixes starting at 1000. A key that quietly kept reading it
    would collapse every one of a carrier's departures on a route and date into a
    single observation.
    """
    assert OBSERVATION_IDENTITY_KEYS == ("search_session_id", *BOOKING_CURVE_KEYS,
                                         "cabin_class")
    assert "departure_time" in OBSERVATION_IDENTITY_KEYS
    assert "flight_number" not in OBSERVATION_IDENTITY_KEYS


# ── shape guarantees the callers rely on ──────────────────────────────────────

def test_order_of_first_appearance_is_preserved():
    rows = [_row(airline_code="6E"), _row(airline_code="AI"), _row(airline_code="6E"),
            _row(airline_code="SG")]
    kept, _ = deduplicate_observation_batch(rows)
    assert [r["airline_code"] for r in kept] == ["6E", "AI", "SG"]


def test_empty_batch_and_idempotence():
    kept, report = deduplicate_observation_batch([])
    assert kept == [] and report["submitted"] == 0 and report["dropped"] == 0

    # Idempotent, which is what makes it safe to run at both the call site (for an
    # honest `rows_submitted`) and inside `insert_observations` (for the guarantee).
    once, _ = deduplicate_observation_batch([_row(), _row(price=5900.0), _row()])
    twice, report = deduplicate_observation_batch(once)
    assert twice == once
    assert report["dropped"] == 0


def test_input_rows_are_not_mutated():
    """The survivors are the caller's own dicts; nothing is rewritten in place."""
    rows = [_row(price=6200.0), _row(price=5900.0)]
    before = [dict(r) for r in rows]
    kept, _ = deduplicate_observation_batch(rows)
    assert rows == before
    assert kept[0] is rows[1]


# ── the two call sites ────────────────────────────────────────────────────────

def test_insert_observations_collapses_before_submitting(monkeypatch):
    """The guarantee lives at the choke point, not at one caller.

    `historical_data_service.insert_observations` is the only code in the project that
    writes `price_history`, so a future caller — a backfill, a second collector —
    inherits the de-duplication without knowing it is there.
    """
    table, insert = MagicMock(), MagicMock()
    table.insert = MagicMock(return_value=insert)

    from backend.database.database import database
    monkeypatch.setattr(database.supabase, "table", MagicMock(return_value=table))

    rows = [_row(price=6200.0), _row(price=5900.0), _row(airline_code="AI", price=7100.0)]
    insert.execute = MagicMock(return_value=MagicMock(data=[{}, {}]))

    assert historical_data_service.insert_observations(rows) == 2
    submitted = table.insert.call_args[0][0]
    assert len(submitted) == 2
    assert sorted(r["price"] for r in submitted) == [5900.0, 7100.0]


@pytest.mark.asyncio
async def test_search_does_not_report_a_duplicate_as_a_persistence_fault():
    """A collapsed duplicate must not be reported as the database losing a row.

    `rows_submitted` is compared against the count the database confirms, and the
    2026-08 fix pass added it precisely so that number could be trusted. Had the
    de-duplication run only inside `insert_observations`, every batch containing a
    repeated provider card would submit fewer rows than the caller counted and the
    search would be marked `degraded` with `persistence_error: submitted 3, database
    persisted 2` — a fabricated database fault, on the field added to stop fabricated
    persistence claims. That is why the call site de-duplicates too.
    """
    provider = {
        "status": STATUS_OK,
        "data": [
            {"price": 6200.0, "currency": "INR", "primary_airline": "6E",
             "departure_time": "2026-07-20T06:10:00"},
            # The same flight again, cheaper: one card duplicated by the scraper.
            {"price": 5900.0, "currency": "INR", "primary_airline": "6E",
             "departure_time": "2026-07-20T06:10:00"},
            {"price": 7100.0, "currency": "INR", "primary_airline": "AI",
             "departure_time": "2026-07-20T19:45:00"},
        ],
    }

    with (
        patch("backend.services.flight_data_service.flight_data_service.search_flights",
              return_value=provider),
        patch("backend.services.historical_data_service.historical_data_service."
              "insert_observations", return_value=2) as mock_insert,
    ):
        result = await flight_search_service.search("DEL", "BOM", "2026-07-20")

    submitted = mock_insert.call_args[0][0]
    assert len(submitted) == 2, "the duplicated card reached the insert"
    assert sorted(r["price"] for r in submitted) == [5900.0, 7100.0]

    meta = result.metadata
    assert meta["rows_submitted"] == 2
    assert meta["rows_persisted"] == 2
    assert meta["provider_duplicate_rows"] == 1
    assert meta["persistence_error"] is None
    assert meta["search_status"] == "success"








