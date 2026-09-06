"""SkyMind Domain Rules — observation provenance.

One definition of "this fare was really observed in the market", because the rule
was previously written out by hand in three places and the three had already
drifted apart:

  * `database._PROVENANCE_SQL` — `is_synthetic IS FALSE AND is_live IS TRUE`,
    mirrored a second time as a PostgREST `.is_()` chain in `_load_from_supabase`;
  * `forecast_evaluation_scheduler._REALISED_FARE_FILTERS` — the same two
    conditions as a tuple of column/value pairs;
  * `services.training_eligibility` — which applied **neither** condition, and
    whose docstring said it "replaces legacy `WHERE is_live = TRUE` overloading".
    It did not replace it: that predicate is still applied, upstream, and it is
    the condition doing the real work.

Why both conditions are needed is recorded at length above `PROVENANCE_SQL` in
`backend/database/database.py`: the migration that added `is_synthetic` gave it
`DEFAULT FALSE`, so the seeded rows read back as authentic, and `is_live` — set
from observed data at ingest rather than by a later migration — is what still
excludes them.

The fare window and the currency rule live here for the same reason: they are
read-side conditions that also have to hold at write time, and writing them out
twice is how the three above drifted. `screen_observation_fares` applies them to
a batch on its way to the database, using these constants and no others.

Everything here is stdlib-only and free of project imports, so any layer can
depend on it.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple, Union

# ── column names ────────────────────────────────────────────────────────────

SYNTHETIC_KEY = "is_synthetic"
LIVE_KEY = "is_live"

# ── the fare window ─────────────────────────────────────────────────────────
#
# Rows outside this range are not treated as observations of the market. The
# same two numbers were written out four times (twice in `database.py`, twice in
# `training_eligibility.py`); they are one rule.
#
# Distinct from `price_model.IMPLAUSIBLE_FARE_FLOOR`, which happens to share the
# lower number but governs something else: whether a *prediction* the model just
# produced may be shown to a user.
MIN_PLAUSIBLE_FARE = 800.0
MAX_PLAUSIBLE_FARE = 60000.0

# ── the currency the corpus is denominated in ────────────────────────────────
#
# Every fare in `price_history` is read as rupees. The window above is in rupees;
# `training_dataset_builder` averages the `price` column without consulting any
# currency; the loaders' predicate is `PROVENANCE_SQL`, which names two boolean
# columns and nothing else. **No query in the project filters on `currency`.** So
# a row whose fare is not in rupees is not a fare in another unit — it is a wrong
# number, and it is wrong in a way that survives every check downstream of it.
#
# This is measured, not hypothetical. 156 rows recorded on 2026-07-19 carry fares
# between ₹58 and ₹105. They are US dollars. `GoogleFlightsProvider.js` finds the
# price line by testing it for '₹' *or* '$' and then strips every non-digit
# character — including the symbol it just matched — so a page Google served in
# dollars yielded a bare number, and the write path stamped "INR" on it from a
# parameter default that no caller had ever passed.
CURRENCY_KEY = "currency"
CORPUS_CURRENCY = "INR"

# ── the predicate, in the three forms callers need ───────────────────────────

#: For raw SQL (SQLAlchemy `text()`).
PROVENANCE_SQL = f"{SYNTHETIC_KEY} IS FALSE AND {LIVE_KEY} IS TRUE"

#: For PostgREST/Supabase query builders: `for col, val in ...: q = q.is_(col, val)`.
#: `.is_()` rather than `.eq()`/`.neq()` on purpose — `NULL <> true` is NULL, so
#: `.neq("is_synthetic", True)` silently drops rows with an unknown label instead
#: of failing closed on them.
PROVENANCE_IS_FILTERS: Tuple[Tuple[str, bool], ...] = (
    (SYNTHETIC_KEY, False),
    (LIVE_KEY, True),
)

_TRUE_TOKENS = frozenset({"true", "t", "yes", "y", "1", "1.0"})
_FALSE_TOKENS = frozenset({"false", "f", "no", "n", "0", "0.0"})


def decode_flag(value: Any) -> Optional[bool]:
    """A boolean column's value as a bool, or None when it does not say.

    Handles what the loaders actually hand back for a Postgres BOOLEAN: a real
    bool, a numpy bool, the strings PostgREST and CSV round-trips produce, and
    None/NaN. Anything else returns None — an unreadable provenance label is not
    a False, and callers fail closed on it rather than guessing.

    Numerics are read the ordinary way: 0 is False, 1 is True. That is worth
    stating because a *third* encoding used to exist — `database._engineer_features`
    remapped this column to 2.0 for live and 1.0 for not-live — under which 1.0
    meant the opposite. It was removed, in part because it made 1.0 ambiguous
    between the two conventions, and in part because it never worked: see the
    comment at that site. Nothing persists the 2.0/1.0 form, so 2.0 is accepted
    here as a truthy legacy value and needs no special case.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    # NaN is the only value not equal to itself; checking it this way keeps this
    # module free of a pandas/numpy import.
    if value != value:
        return None
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    # numpy.bool_ and friends: they are not `bool` instances but do define
    # __bool__. Anything without one is not a flag.
    try:
        return bool(value)
    except (TypeError, ValueError):
        return None


def fare_is_plausible(price: Any) -> bool:
    """Whether `price` sits inside the fare window. Unreadable prices are not."""
    if price is None or price != price:
        return False
    try:
        value = float(price)
    except (TypeError, ValueError):
        return False
    return MIN_PLAUSIBLE_FARE <= value <= MAX_PLAUSIBLE_FARE


# ── currency, read rather than assumed ───────────────────────────────────────

#: Only what a provider on this path can actually emit, plus the symbols the
#: scraper matches on. Deliberately short: an alias table is a place for a guess
#: to hide, and every code here other than `CORPUS_CURRENCY` leads to the same
#: outcome — the row is refused — so the table's only real job is to make the
#: refusal *say which currency it saw*.
#:
#: "$" is a locale inference, not a reading: the symbol is shared by USD, CAD,
#: AUD, SGD and others. It is mapped to USD because Google Flights renders it for
#: dollars on the pages this scraper visits, and because the mapping cannot change
#: any decision — every one of those codes is refused identically. If a caller
#: ever needs to *act* on the distinction, this is the wrong table to read.
_CURRENCY_ALIASES = {
    "INR": "INR", "RS": "INR", "RS.": "INR", "₹": "INR",
    "USD": "USD", "US$": "USD", "$": "USD",
    "EUR": "EUR", "€": "EUR",
    "GBP": "GBP", "£": "GBP",
    "AED": "AED", "SGD": "SGD",
}


def decode_currency(value: Any) -> Optional[str]:
    """`value` as a currency code, or None when it does not say.

    None is the answer for absent, blank and unrecognised input, and it is
    **not** a synonym for `CORPUS_CURRENCY`. That distinction is the whole point:
    `flight_data_service` read an absent currency as `"INR"` in its FX loop
    (`(f.get("currency") or "INR").upper()`) and therefore concluded that a fare
    of unknown denomination was already in the target currency and needed no
    conversion; `format_payload` did the same thing with a parameter default. Two
    layers independently turned "nobody said" into "rupees".
    """
    if value is None:
        return None
    if value != value:  # NaN, without importing numpy
        return None
    token = str(value).strip().upper()
    if not token:
        return None
    return _CURRENCY_ALIASES.get(token)


def fare_currency_is_corpus_currency(record: Union[Mapping[str, Any], Dict[str, Any]]) -> bool:
    """Whether one record's fare is denominated in the currency the corpus uses.

    Fails closed on an absent or unreadable currency, for the reason in
    `decode_currency`. Deliberately **not** folded into
    `has_authentic_provenance`: that function's contract is "the same predicate
    the loaders apply in SQL", and the SQL has no currency condition. Adding one
    there would recreate exactly the drift `PROVENANCE_SQL` exists to prevent —
    and it would also silently exclude every already-stored row, whose `currency`
    this module has never measured.
    """
    return decode_currency(record.get(CURRENCY_KEY)) == CORPUS_CURRENCY


def screen_observation_fares(
    records: Any,
) -> Tuple[list, Dict[str, Any]]:
    """`(kept, report)` — the observations fit to store, and why the rest are not.

    Two refusals, checked in this order, one reason recorded per row so the counts
    sum to `dropped`:

      1. **The fare is not in `CORPUS_CURRENCY`,** or does not say what it is in.
         A foreign fare is dropped rather than stored-and-labelled, because
         nothing downstream reads the column: stored, it becomes a ₹6,000 route
         average pulled toward a $70 number. Dropping costs one observation;
         storing costs the route's statistics.
      2. **The fare is outside the window** `MIN_PLAUSIBLE_FARE`–`MAX_PLAUSIBLE_FARE`.

    Why a write-side drop is safe here, when it usually is not: neither bound is
    new. Both are the constants the loaders already apply, so a row this refuses
    is exactly a row no loader would have used. If the window is ever wrong it is
    equally wrong at read time, and nothing is lost that would have been read.

    The currency check is the load-bearing one, and the window is not a substitute
    for it. The window catches the measured ₹58–₹105 batch because those dollar
    figures happen to be small; it does not catch a $900 fare, which lands at 900
    — inside the window, indistinguishable from a very cheap rupee fare, and off
    by a factor of ~83.

    Order-preserving, and it never mutates the input rows.
    """
    kept: list = []
    currencies_seen: Dict[str, int] = {}
    foreign = 0
    unreadable = 0
    implausible = 0
    worst: Optional[float] = None

    for record in records or []:
        if not isinstance(record, Mapping):
            # Not an observation at all. Refuse it here rather than letting the
            # database decide: a non-mapping in the batch fails the whole insert.
            unreadable += 1
            continue

        code = decode_currency(record.get(CURRENCY_KEY))
        if code is None:
            unreadable += 1
            continue
        currencies_seen[code] = currencies_seen.get(code, 0) + 1
        if code != CORPUS_CURRENCY:
            foreign += 1
            continue

        price = record.get("price")
        if not fare_is_plausible(price):
            implausible += 1
            try:
                value = float(price)
            except (TypeError, ValueError):
                value = None
            if value is not None and (worst is None or abs(value - MIN_PLAUSIBLE_FARE) > abs(worst - MIN_PLAUSIBLE_FARE)):
                worst = value
            continue

        kept.append(record)

    submitted = foreign + unreadable + implausible + len(kept)
    return kept, {
        "submitted": submitted,
        "kept": len(kept),
        "dropped": foreign + unreadable + implausible,
        "dropped_foreign_currency": foreign,
        "dropped_unreadable_currency": unreadable,
        "dropped_implausible_fare": implausible,
        "currencies_seen": currencies_seen,
        "worst_dropped_fare": worst,
    }


def has_authentic_provenance(record: Union[Mapping[str, Any], Dict[str, Any]]) -> bool:
    """Whether one record satisfies the same predicate the loaders apply in SQL.

    Fails closed: a record that omits either column, or carries a value
    `decode_flag` cannot read, is not authentic. `is_synthetic` missing used to be
    read as False by every caller that checked it at all, which is how a corpus
    whose labels had been defaulted in by a migration passed for observed data.
    """
    synthetic = decode_flag(record.get(SYNTHETIC_KEY))
    if synthetic is not False:
        return False
    return decode_flag(record.get(LIVE_KEY)) is True
