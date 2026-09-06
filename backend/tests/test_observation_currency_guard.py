"""Write-side currency guard: a fare is only storable if its denomination is known.

Nothing in this project filters `price_history` on `currency`. The fare window is in
rupees, `training_dataset_builder` averages the `price` column without consulting any
currency, and the loaders' predicate names two boolean columns and nothing else. So a
row whose fare is not in rupees is not a fare in another unit — it is a wrong number,
and it is wrong in a way that survives every check downstream of it.

That is measured, not hypothetical: 156 rows recorded on 2026-07-19 carry fares
between ₹58 and ₹105, and they are US dollars. The defect was implemented three times
independently — `GoogleFlightsProvider.js` locates the price line by testing it for
'₹' or '$' and then strips the symbol it just matched; `flight_data_service`'s FX loop
read `(f.get("currency") or "INR").upper()`, so a fare of unknown denomination was
declared to already be in the target currency and skipped; and `format_payload`'s
`currency: str = "INR"` default stamped rupees while the one production caller never
passed the argument.

These tests cover the Python half of the fix (AUDIT-FIXES.md §48). The JS half —
emitting the matched symbol as a currency — has no test here because this suite does
not run Node; it is verified by the field-coverage probe the user runs on Windows.

The last section covers the display path, which is where the defect was visible: the
write-side screen keeps a wrong number out of the corpus, but three further copies of
the same default were rendering that number to the user with a rupee symbol on it.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.domain.provenance import (
    CORPUS_CURRENCY,
    MAX_PLAUSIBLE_FARE,
    MIN_PLAUSIBLE_FARE,
    decode_currency,
    fare_currency_is_corpus_currency,
    has_authentic_provenance,
    screen_observation_fares,
)
from backend.services.flight_data_service import STATUS_OK
from backend.services.flight_formatter import FlightSearchFormatter
from backend.services.flight_normalizer import FlightNormalizer
from backend.services.flight_search_service import flight_search_service
from backend.services.historical_data_service import historical_data_service
from backend.services.ingestion_controller import MarketDataController

SESSION = "22222222-2222-4222-8222-222222222222"


def _row(**over):
    """A `get_db_payload`-shaped observation with a complete identity and a real fare."""
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


# ── decode_currency: absent is not INR ────────────────────────────────────────

@pytest.mark.parametrize("value", [None, "", "   ", "rupees", "Rupee", "XYZ", "IN", 0, [], {}])
def test_unreadable_currency_is_none_not_the_corpus_currency(value):
    """The whole point of the fix: "nobody said" must not resolve to rupees.

    Every one of these used to become INR by one of two routes — the `or "INR"` in
    the FX loop or the parameter default in `format_payload`.
    """
    assert decode_currency(value) is None


@pytest.mark.parametrize("value,expected", [
    ("INR", "INR"), ("inr", "INR"), (" inr ", "INR"), ("₹", "INR"), ("Rs", "INR"), ("rs.", "INR"),
    ("USD", "USD"), ("usd", "USD"), ("$", "USD"), ("US$", "USD"),
    ("EUR", "EUR"), ("€", "EUR"), ("GBP", "GBP"), ("£", "GBP"),
    ("AED", "AED"), ("SGD", "SGD"),
])
def test_readable_currencies_decode(value, expected):
    assert decode_currency(value) == expected


def test_nan_currency_is_none():
    """A pandas round-trip turns a NULL text column into NaN, not None."""
    assert decode_currency(float("nan")) is None


def test_fare_currency_predicate_is_the_corpus_currency_only():
    assert fare_currency_is_corpus_currency({"currency": "INR"}) is True
    assert fare_currency_is_corpus_currency({"currency": "₹"}) is True
    assert fare_currency_is_corpus_currency({"currency": "USD"}) is False
    assert fare_currency_is_corpus_currency({}) is False
    assert fare_currency_is_corpus_currency({"currency": None}) is False


# ── the screen ────────────────────────────────────────────────────────────────

def test_a_dollar_fare_is_refused_even_though_the_number_looks_ordinary():
    """The load-bearing case, and the one the fare window cannot catch.

    A $900 fare lands in the `price` column as 900 — inside the window, and
    indistinguishable from a very cheap rupee fare. Off by a factor of about 83.
    """
    kept, report = screen_observation_fares([_row(price=900.0, currency="USD")])
    assert kept == []
    assert report["dropped"] == 1
    assert report["dropped_foreign_currency"] == 1
    assert report["dropped_implausible_fare"] == 0
    assert report["currencies_seen"] == {"USD": 1}


def test_an_undeclared_currency_is_refused():
    """`get_db_payload` drops None, so the row simply arrives without the key."""
    kept, report = screen_observation_fares([_row(currency=None)])
    assert kept == []
    assert report["dropped_unreadable_currency"] == 1
    assert report["currencies_seen"] == {}


def test_a_rupee_fare_inside_the_window_is_kept_unchanged():
    row = _row()
    kept, report = screen_observation_fares([row])
    assert kept == [row]
    assert kept[0] is row, "the survivor must be the caller's own dict"
    assert report["dropped"] == 0
    assert report["currencies_seen"] == {CORPUS_CURRENCY: 1}


def test_the_measured_dollar_batch_is_refused_by_currency_not_by_luck():
    """₹58–₹105: the actual stored rows, and both guards would fire on them.

    The currency check is the reason they are refused. The window happens to catch
    them too, because those dollar figures are small — which is exactly why the
    window is not a substitute for the check.
    """
    kept, report = screen_observation_fares([
        _row(price=58.0, currency="USD"), _row(price=105.0, currency="USD"),
    ])
    assert kept == []
    assert report["dropped_foreign_currency"] == 2
    # One reason per row: currency is checked first, so neither is also counted
    # against the window.
    assert report["dropped_implausible_fare"] == 0


@pytest.mark.parametrize("price", [None, 0, -1, 58.0, MIN_PLAUSIBLE_FARE - 0.01,
                                   MAX_PLAUSIBLE_FARE + 0.01, 1e9, "cheap", float("nan")])
def test_fares_outside_the_window_are_refused(price):
    kept, report = screen_observation_fares([_row(price=price)])
    assert kept == []
    assert report["dropped_implausible_fare"] == 1


@pytest.mark.parametrize("price", [MIN_PLAUSIBLE_FARE, MAX_PLAUSIBLE_FARE, 6200.0])
def test_the_window_is_inclusive_at_both_bounds(price):
    kept, _ = screen_observation_fares([_row(price=price)])
    assert len(kept) == 1


def test_one_reason_per_row_so_the_counts_sum_to_dropped():
    """A report whose parts do not add up cannot be used to explain a shortfall."""
    kept, report = screen_observation_fares([
        _row(),                                    # kept
        _row(price=70.0, currency="USD"),          # foreign (and small, but counted once)
        _row(currency=None),                       # unreadable
        _row(price=12.0),                          # window
        _row(price=9_000_000.0),                   # window
        "not a mapping at all",                    # unreadable
    ])
    assert len(kept) == 1
    assert report["submitted"] == 6
    assert report["kept"] == 1
    assert report["dropped"] == 5
    assert (report["dropped_foreign_currency"]
            + report["dropped_unreadable_currency"]
            + report["dropped_implausible_fare"]) == report["dropped"]
    assert report["dropped_foreign_currency"] == 1
    assert report["dropped_unreadable_currency"] == 2
    assert report["dropped_implausible_fare"] == 2
    assert report["worst_dropped_fare"] == 9_000_000.0


def test_order_is_preserved_and_input_is_not_mutated():
    rows = [_row(airline_code="6E"), _row(airline_code="AI", currency="USD"),
            _row(airline_code="SG")]
    before = [dict(r) for r in rows]
    kept, _ = screen_observation_fares(rows)
    assert [r["airline_code"] for r in kept] == ["6E", "SG"]
    assert rows == before


def test_empty_and_none_batches():
    for batch in ([], None):
        kept, report = screen_observation_fares(batch)
        assert kept == [] and report["submitted"] == 0 and report["dropped"] == 0


def test_screening_is_idempotent():
    """Safe to run at the call site for an honest count and again at the writer."""
    once, _ = screen_observation_fares([_row(), _row(price=70.0, currency="USD")])
    twice, report = screen_observation_fares(once)
    assert twice == once
    assert report["dropped"] == 0


# ── the read predicate is deliberately unchanged ──────────────────────────────

def test_the_currency_rule_is_not_folded_into_the_provenance_predicate():
    """`has_authentic_provenance` mirrors the loaders' SQL, and the SQL has no
    currency condition. Adding one here would recreate exactly the drift that
    `provenance.py` exists to prevent, and would silently exclude every already
    stored row, whose `currency` has never been measured.
    """
    usd = {"is_synthetic": False, "is_live": True, "currency": "USD", "price": 900.0}
    assert has_authentic_provenance(usd) is True
    assert fare_currency_is_corpus_currency(usd) is False

    from backend.domain import provenance
    assert "currency" not in provenance.PROVENANCE_SQL
    assert all(col != "currency" for col, _ in provenance.PROVENANCE_IS_FILTERS)


# ── format_payload: it reads the currency now, it does not assume one ─────────

def test_format_payload_no_longer_stamps_inr_on_an_unstated_currency():
    payload = MarketDataController.format_payload(
        origin_code="DEL", destination_code="BOM", airline_code="6E",
        price=5500.0, departure_date="2026-08-01", days_until_dep=10,
    )
    assert payload["currency"] is None
    assert "currency" not in MarketDataController.get_db_payload(payload)


@pytest.mark.parametrize("stated,expected", [
    ("INR", "INR"), ("₹", "INR"), ("USD", "USD"), ("$", "USD"), ("nonsense", None),
])
def test_format_payload_decodes_what_the_provider_stated(stated, expected):
    payload = MarketDataController.format_payload(
        origin_code="DEL", destination_code="BOM", airline_code="6E",
        price=5500.0, departure_date="2026-08-01", days_until_dep=10,
        currency=stated,
    )
    assert payload["currency"] == expected


# ── ordering: screen before collapsing ────────────────────────────────────────

def test_a_dollar_quote_must_not_take_a_rupee_quote_down_with_it(monkeypatch):
    """The ordering bug this fix was designed around, asserted at the writer.

    `deduplicate_observation_batch` keeps the *lowest* fare in an identity group. If
    the screen ran after it, a group holding the same flight quoted once in dollars
    (70) and once in rupees (6,000) would collapse to the dollar row — which the
    screen would then drop, losing a good observation to a bad one. Screening first
    means the de-duplicator only ever sees storable fares.
    """
    table, insert = MagicMock(), MagicMock()
    table.insert = MagicMock(return_value=insert)
    insert.execute = MagicMock(return_value=MagicMock(data=[{}]))

    from backend.database.database import database
    monkeypatch.setattr(database.supabase, "table", MagicMock(return_value=table))

    rows = [_row(price=70.0, currency="USD"), _row(price=6000.0)]
    assert historical_data_service.insert_observations(rows) == 1

    submitted = table.insert.call_args[0][0]
    assert [r["price"] for r in submitted] == [6000.0], (
        "the dollar quote survived de-duplication and the rupee observation was lost"
    )


def test_a_fully_refused_batch_is_never_submitted(monkeypatch):
    """Nothing storable means no insert at all, and a count of 0 rather than -1.

    -1 means "the database did not say". It must not be returned for a batch the
    database was never asked about.
    """
    table = MagicMock()
    from backend.database.database import database
    monkeypatch.setattr(database.supabase, "table", MagicMock(return_value=table))

    assert historical_data_service.insert_observations(
        [_row(currency="USD"), _row(currency=None)]
    ) == 0
    assert not table.insert.called


# ── the call site reports the shortfall instead of hiding it ──────────────────

@pytest.mark.asyncio
async def test_search_reports_refused_rows_and_not_a_persistence_fault():
    """A refused fare is a collection shortfall, not the database losing a row.

    `rows_submitted` is compared against the count the database confirms, so the
    screen has to run before that number is taken — otherwise every batch containing
    a foreign fare reports `persistence_error: submitted 3, database persisted 2`, a
    fabricated database fault on the very field added to stop fabricated persistence
    claims. The refusal is published as its own metadata instead, with the currencies
    seen: a batch reading `{"USD": 20}` means Google served the page in dollars.
    """
    provider = {
        "status": STATUS_OK,
        "data": [
            {"price": 6200.0, "currency": "INR", "primary_airline": "6E",
             "departure_time": "2026-07-20T06:10:00"},
            {"price": 70.0, "currency": "USD", "primary_airline": "AI",
             "departure_time": "2026-07-20T19:45:00"},
            # No currency at all: what the scraper emitted before the JS half of §48.
            {"price": 7100.0, "primary_airline": "SG",
             "departure_time": "2026-07-20T21:30:00"},
        ],
    }

    with (
        patch("backend.services.flight_data_service.flight_data_service.search_flights",
              return_value=provider),
        patch("backend.services.historical_data_service.historical_data_service."
              "insert_observations", return_value=1) as mock_insert,
    ):
        result = await flight_search_service.search("DEL", "BOM", "2026-07-20")

    submitted = mock_insert.call_args[0][0]
    assert [r["price"] for r in submitted] == [6200.0]

    meta = result.metadata
    assert meta["rows_submitted"] == 1
    assert meta["rows_persisted"] == 1
    assert meta["refused_rows"] == 2
    assert meta["refused_currencies"] == {"INR": 1, "USD": 1}
    assert meta["persistence_error"] is None


# ── the display half: what the user actually saw ──────────────────────────────
#
# The write path above stops a wrong number entering the corpus. It does nothing
# about the same number being shown to the user, and three more copies of the
# identical default lived on that path: `NormalizedFlight.currency: str = "INR"`,
# and `.get("currency", "INR")` in each of `normalize_db_flight` and
# `normalize_mcp_flight`. With `format_currency` rendering `₹{int(price):,}` for
# "INR", a $58 fare displayed as ₹58 — which is why a batch of dollar quotes sat
# in the UI for weeks looking like unusually cheap flights.

def test_a_provider_card_without_a_currency_is_not_displayed_as_rupees():
    flight = FlightNormalizer.normalize_mcp_flight(
        {"price": 58.0, "primary_airline": "AI", "primary_airline_name": "Air India",
         "departure_time": "2026-07-20T06:10:00"},
        "DEL", "BOM", "2026-07-20",
    )
    assert flight is not None
    assert flight.currency is None
    presented = FlightSearchFormatter.to_presentation(flight)
    assert presented["price"]["currency"] is None
    assert "₹" not in presented["price_formatted"]
    assert presented["price_formatted"] == "58.00"


def test_a_dollar_card_is_displayed_in_dollars():
    flight = FlightNormalizer.normalize_mcp_flight(
        {"price": 58.0, "currency": "$", "primary_airline": "AI",
         "primary_airline_name": "Air India", "departure_time": "2026-07-20T06:10:00"},
        "DEL", "BOM", "2026-07-20",
    )
    assert flight.currency == "USD"
    assert FlightSearchFormatter.to_presentation(flight)["price_formatted"] == "$58.00"


def test_a_cached_row_with_no_measured_currency_stays_unstated():
    """Every row already in `price_history` is in this position.

    `currency` has never been measured for the stored corpus, so a cached result
    must not acquire a denomination on the way back out — the read predicate
    deliberately does not filter on it (see the test above), which means these rows
    are still served.
    """
    flight = FlightNormalizer.normalize_db_flight(
        {
            "airline_code": "6E", "airline_name": "IndiGo", "price": 6200.0,
            "origin_code": "DEL", "destination_code": "BOM",
            "departure_time": "2026-07-20T06:10:00", "cabin_class": "ECONOMY",
        },
        "DEL", "BOM", "2026-07-20",
    )
    assert flight is not None
    assert flight.currency is None
