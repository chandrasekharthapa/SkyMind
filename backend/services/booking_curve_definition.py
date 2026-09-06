"""Centralized Booking Curve Definition.

Establishes single-source-of-truth grouping keys, ordering, and helper utilities
for constructing chronological booking curves across SkyMind pipelines.

This module is the only place allowed to answer three questions, because the
2026-08 audit found each of them answered differently in different files:

1. *What is one booking curve?*  `BOOKING_CURVE_KEYS`, five columns, the fifth
   being `departure_time` — the scheduled local departure instant, which is what
   distinguishes one of a carrier's flights on a route from the next.
   `backend/ml/features/booking_curve.py` grouped on four of the five and
   `backend/database/database.py` grouped on two, so a shift on what was called
   "the same flight's price history" crossed between different flights and, in
   the two-key case, between different departure dates.

2. *Which timestamp means "earlier"?*  `ORDERING_TIMESTAMP_KEY`, falling back to
   `FALLBACK_TIMESTAMP_KEY`.  The target join was aligned on one and the lag
   features on the other, so the two disagreed about the order of the very rows
   they were paired across.  `resolve_ordering_timestamp_column` is now the only
   sanctioned way to pick it.

3. *What is a lag of n days?*  `price_at_lag`, an as-of lookup.  Every previous
   definition was `groupby(...).shift(n)`, which is n *observations* back, not n
   days.  Under an irregular ingestion cadence — and with several flights
   interleaved into one group by defect 1 — "3 rows ago" ranged from minutes to
   weeks while the feature was named `price_change_3d` and the model put 37% of
   its importance on it.

4. *What is the supervised label?*  `attach_future_target`, built on
   `price_at_horizon`, the mirror of `price_at_lag`.  There were two rival target
   joins — `training_dataset_builder.build` and `PriceModel._build_shifted_dataset`
   — disagreeing on whether the label was the first or the cheapest fare of the
   target day, both joining on calendar-date equality over four keys, and only
   the second covered by any test.  Neither carried any per-flight component, so
   the label was routinely another flight's later fare; and at horizon 0 the
   builder assigned `target_price = price` on the same row, which is why
   `MIN_TRAINABLE_HORIZON_DAYS` exists.
"""

from typing import List, Tuple, Dict, Any, Optional, Sequence
import numpy as np
import pandas as pd

# What makes two observations the same flight's price history.
#
# The fifth component was `flight_number` until 2026-09-03. It was changed to
# `departure_time` because the flight number does not exist in the data and
# cannot be made to: the only wired provider is Google Flights, and a live
# DEL->BOM fetch (130 cards, 65 flights, 2026-09-24 departure) contained zero
# carrier-coded flight numbers anywhere in the page text. The scraper now
# reports `null` for it by measurement — see the comment in
# `india-flight-mcp/src/providers/GoogleFlightsProvider.js`. MakeMyTrip, the one
# plausible second source, was measured dead on the same day and its scraper
# deleted: its search widget renders no interactive elements at all under
# automation, and its results URL answers with a six-character stub body. So
# Google Flights is not merely the provider that happens to be wired — it is the
# only one, and this key may not assume a field it does not publish.
#
# So the choice was not between two identities but between an identity and none.
# `curve_identity_is_complete` requires every component non-blank, so with a NULL
# flight number **no row in the corpus can carry a label** — not on any cadence,
# not at any horizon. Measured on those same 65 live rows: the old five keys
# yield **5** distinct identities (they collapse onto the five airline codes,
# pooling 29 IndiGo departures into one "curve"); substituting `departure_time`
# yields **64**, and the single collision is an exact duplicate card rather than
# two flights.
#
# `departure_time` is a sound identity rather than a convenient one. A carrier's
# scheduled departure instant on a route on a date names one flight, it is stable
# across collection runs because it is the published schedule rather than an
# observation timestamp, and it is precisely the granularity `flight_number` was
# added to obtain. It is also already carried by the serving path, which resolves
# it from the same snapshot entry as the fare it is quoting.
#
# Two consequences a reader must not be surprised by. `departure_date` is now
# functionally redundant — `departure_time` determines it — and is kept because
# it is what the database indexes and what several callers read off the key; a
# redundant component cannot split a group, so it is harmless. And the column is
# added by migration 001: until that is applied, `departure_time` is absent from
# `price_history`, `curve_identity_mask` returns False for every row by design,
# and nothing trains. That is the honest state, not a regression.
#
# Naming the key was necessary and was not sufficient, and the gap is worth
# stating here because this is where a reader looks for the guarantee. Absent
# column and NULL value are different failures. `attach_future_target` raises on
# the first, so "nothing trains" was true of it. The second used to train: the
# migration adds `departure_time` with no backfill, so every pre-migration row
# would have held NULL, `curve_identity_mask` would have returned False for all of
# them, and `_price_at_offset` did not consult the mask — `merge_asof(by=...)`
# factorises a null to a value that matches other nulls, so the 29 pooled IndiGo
# departures above would have come back as one curve and labelled each other.
# Applying the migration was the trigger. The mask is applied inside
# `_price_at_offset` now, on both sides of the join, which is the only place that
# makes the label and the lag features agree about which rows have a curve.
BOOKING_CURVE_KEYS: List[str] = [
    "origin_code",
    "destination_code",
    "airline_code",
    "departure_time",
    "departure_date"
]

# The subset of the key whose values are IATA-style codes, and are therefore
# compared case-insensitively. `get_booking_curve_group_key` upper-cases these and
# leaves the temporal components alone.
_CASE_NORMALISED_KEYS: Tuple[str, ...] = (
    "origin_code",
    "destination_code",
    "airline_code",
)

ORDERING_TIMESTAMP_KEY: str = "search_timestamp"
FALLBACK_TIMESTAMP_KEY: str = "recorded_at"

# A lag of n days resolves to the most recent observation on the same curve at or
# before t - n days. That observation is accepted only if it is no more than
# `n * LAG_TOLERANCE_FRACTION` days older than the point asked for (floored at
# MIN_LAG_TOLERANCE_DAYS), so a 1-day lag cannot be satisfied by a fare observed
# a fortnight ago. When nothing qualifies the feature is null: XGBoost handles
# NaN natively, and "no comparable earlier observation" is a fact about the
# route, not a zero.
LAG_TOLERANCE_FRACTION: float = 0.5
MIN_LAG_TOLERANCE_DAYS: float = 0.5

# The smallest horizon that is a *learnable* target, and the reason it is not 0.
#
# At horizon 0 the label is the price on the same row as the features. Every
# price-derived feature is then a function of the target by construction, so the
# fit is an identity and its r² is a restatement of the join, not a measurement
# of skill. No masking, shifting or windowing can detect that: the leaking row
# *is* the labelled row, so any check that compares timestamps sees nothing
# wrong. `attach_future_target` therefore refuses it rather than reporting a
# score. Note that the forward window below makes this mechanical — at horizon 0
# the window [t, t] collapses onto the observation itself.
MIN_TRAINABLE_HORIZON_DAYS: int = 1

# The horizons the system trains and serves a model for, in days ahead.
#
# Lifted here from `PriceModel.__init__`, where it was the literal `[1, 3, 7]`,
# because it is not only the trainer's business: a data diagnostic has to grade a
# corpus against the horizons that will actually be trained, and importing the
# trainer to learn them would drag xgboost into a pandas-only tool. This module
# already owns `MIN_TRAINABLE_HORIZON_DAYS`, which is the rule that decides what
# may appear in this tuple, so it is the one place both can read.
#
# Every entry must be >= MIN_TRAINABLE_HORIZON_DAYS; `attach_future_target`
# enforces that per call rather than trusting the declaration.
SUPPORTED_TRAINING_HORIZONS: Tuple[int, ...] = (1, 3, 7)

# Observations per rolling window, and the minimum needed for a dispersion
# figure. Pandas' rolling .std() is the sample standard deviation (ddof=1); any
# inference-side counterpart must match it, which `rolling_price_statistics`
# guarantees by being the single implementation both paths call.
ROLLING_WINDOW_OBSERVATIONS: int = 10
MIN_OBSERVATIONS_FOR_STD: int = 2

# Floor on the elapsed days used as a slope denominator. Two observations taken
# seconds apart must not divide a rupee difference by ~0 and report a slope of
# ₹10^5/day.
MIN_SLOPE_DELTA_DAYS: float = 0.1


def resolve_ordering_timestamp_column(df: pd.DataFrame) -> Optional[str]:
    """The *preferred* column meaning "when this fare was observed", if present.

    Returns None when neither candidate is present, which callers must treat as
    "this frame cannot be ordered" rather than substituting row position.

    A present column is not the same as a populated one. `ordering_timestamps`
    coalesces per row for that reason, and this function stays column-level
    because its callers use it to name the column in a log line or an artifact's
    metadata. A caller must not read "not None" here as "every row can be
    ordered" — ask `ordering_timestamps(df).notna()` for that.
    """
    for candidate in (ORDERING_TIMESTAMP_KEY, FALLBACK_TIMESTAMP_KEY):
        if candidate in df.columns:
            return candidate
    return None


def ordering_timestamps(df: pd.DataFrame) -> pd.Series:
    """Parsed, UTC-normalised observation times, indexed like `df`.

    `search_timestamp` per row where it parses, `recorded_at` per row where it
    does not. The coalesce is *per observation*, not per column, and that is the
    whole point: this used to resolve one column for the entire frame and read
    only that, so a frame where `search_timestamp` was present but NULL came back
    all-`NaT`. `_price_at_offset` then hit its `if not usable.any()` early return,
    every lag feature and the supervised label itself came out NaN, and
    `attach_future_target` dropped the whole frame. Nothing raised: the training
    frame simply arrived empty.

    That hazard is currently latent rather than live, and the distinction is
    worth keeping straight because an earlier version of this docstring asserted
    the live version of it. It claimed every pre-migration `price_history` row
    holds a NULL `search_timestamp`. Measured 2026-09-03 on a 35,894-row export:
    the column is populated on all 35,894, so no row is in that state today. It
    is reachable — any insert that omits the column stores NULL, and the column
    is nullable — and a single such row is enough to lose that row's label under
    the per-column reader, which is why the coalesce is per observation anyway.

    Coalescing is also what the writer does. `ingestion_controller` line 125
    resolves a missing `search_timestamp` to `recorded_at` before insert, so for
    a row it wrote the two columns are the same instant unless the provider
    reported its own search time — seconds earlier at most. A reader that
    refused the fallback disagreed with the writer about the same fact, which is
    the class of defect this module exists to close. The residual skew is
    bounded by ingest latency and cannot move an as-of match: the tightest
    tolerance any caller uses is `MIN_LAG_TOLERANCE_DAYS` (half a day) and the
    tightest slope denominator is `MIN_SLOPE_DELTA_DAYS` (a tenth of one).

    Normalising to UTC is not cosmetic. `price_history.recorded_at` arrives
    tz-aware from Supabase while a synthesised or CSV-loaded frame may be naive,
    and `pd.merge_asof` refuses to compare the two. Mixing them also silently
    breaks the inference path, where `datetime.fromisoformat` produces a naive
    value for a timestamp with no offset and the current time is tz-aware.

    `format="ISO8601"` is load-bearing, not a way to quiet a warning. Without it
    pandas infers one format from the first non-null element and coerces every
    element that does not match it to `NaT` — so on
    `["...T10:00:00.123456Z", "...T10:00:01Z"]` the second observation is silently
    dropped. That pair is not hypothetical: `datetime.isoformat()` omits the
    microseconds field when it is zero, so any column mixing values from Supabase
    and from Python holds both shapes. The `UserWarning: Could not infer format`
    this used to emit fired on the *safe* path — inference having failed, pandas
    fell back to per-element parsing and got every row right. The lossy path was
    the silent one. `errors="coerce"` still yields `NaT` for a value that is not
    ISO-8601 at all, which is the correct answer: an observation with no readable
    time has no position on its booking curve.
    """
    empty = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    if resolve_ordering_timestamp_column(df) is None:
        return empty

    resolved = empty
    for candidate in (ORDERING_TIMESTAMP_KEY, FALLBACK_TIMESTAMP_KEY):
        if candidate not in df.columns:
            continue
        parsed = pd.Series(
            pd.to_datetime(
                df[candidate], errors="coerce", utc=True, format="ISO8601"
            ).values,
            index=df.index,
            dtype="datetime64[ns, UTC]",
        )
        # `fillna` and not assignment: an earlier candidate that parsed for this
        # row wins, so the preference order above is still what decides when
        # both columns hold a value.
        resolved = resolved.fillna(parsed)
    return resolved


def observed_at_of_record(record: Dict[str, Any]) -> Optional[pd.Timestamp]:
    """`ordering_timestamps`' rule for a single record, or None.

    The row-level counterpart, for the callers that work on one dict at a time
    rather than a frame. It exists so those callers do not hand-roll the
    preference order a fifth time: the 2026-08 audit found four hand-written
    copies of it, in three mutually contradictory orders, two of which preferred
    `recorded_at` — the insert time — over the search instant the writer itself
    treats as authoritative.

    Returns None rather than substituting the current time. A row with no
    observation time is a row whose position on the booking curve is unknown,
    and stamping it with the moment the reader happened to run turns a gap in
    the corpus into a fabricated observation.

    `format="ISO8601"` for the same reason `ordering_timestamps` passes it, plus
    one specific to this pair: without it the two functions accept different
    inputs. A value like `"15/08/2026"` is parsed here by dateutil and coerced to
    `NaT` there, so the row-level and frame-level answers to "when was this
    observed" would disagree — which is precisely the divergence this module was
    written to remove.
    """
    for candidate in (ORDERING_TIMESTAMP_KEY, FALLBACK_TIMESTAMP_KEY):
        raw = record.get(candidate)
        if raw is None:
            continue
        parsed = pd.to_datetime(raw, errors="coerce", utc=True, format="ISO8601")
        if parsed is not pd.NaT and not pd.isna(parsed):
            return parsed
    return None


def curve_group_columns(df: pd.DataFrame) -> List[str]:
    """The booking-curve key columns actually present on `df`.

    A caller that grouped on a hand-typed subset is the defect this exists to
    prevent, so callers pass the frame and take what they are given.
    """
    return [k for k in BOOKING_CURVE_KEYS if k in df.columns]


def _identifies(value: Any) -> bool:
    """Whether one key component names something."""
    if value is None or value is pd.NaT:
        return False
    if isinstance(value, float) and np.isnan(value):
        return False
    return str(value).strip() != ""


def curve_identity_is_complete(record: Dict[str, Any]) -> bool:
    """Whether `record` names a booking curve, all five components of it.

    A partial key is not a curve. `get_booking_curve_group_key` renders a missing
    component as the string `"NONE"`, so two observations that each lack a
    departure instant produce the *same* key and are treated as one flight's
    price history — which is defect 1 of this module's header returning through
    the back door, since `.shift(1)` across that group crosses between different
    flights again. A grouped frame reaches the same place by a different route:
    pandas' `dropna=False` gives every null-keyed row one shared group.

    The serving path fails the other way. Its query carried no per-flight
    component at all, so the key was `(..., "NONE", ...)` while every retrieved
    history row carried a real one; nothing matched, and the curve features were
    computed from the single fare being quoted — `observation_count` 1.0,
    `days_since_first_observation` 0.0, `booking_curve_progress` 0.0 and all four
    `rolling_*` statistics equal to that fare. Those are not the statistics of a
    short curve, they are the statistics of a curve that does not exist, and the
    model was fitted on the real ones.

    Returning False for a whole corpus is a supported outcome, not a bug to route
    around. Before migration 001 is applied there is no `departure_time` column,
    so every row is unidentifiable and the honest report is that nothing can be
    trained — see the note above `BOOKING_CURVE_KEYS`. A caller that responds by
    dropping the missing component from the key has reintroduced defect 1.

    Callers must treat False as "this observation has no curve": every
    curve-derived feature is unknown, which is NaN, and not a window of length 1.
    """
    return all(_identifies(record.get(key)) for key in BOOKING_CURVE_KEYS)


# Alternative spellings a record may carry for a curve-key column. The retrieval
# and prediction-context paths hand back rows using the short names; `price_history`
# uses the `_code` suffix. Only these three have ever had aliases — the temporal
# components are spelled one way everywhere.
CURVE_KEY_ALIASES: Dict[str, Tuple[str, ...]] = {
    "origin_code": ("origin",),
    "destination_code": ("destination",),
    "airline_code": ("airline",),
}


def curve_identity_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """The five curve-key components of `record`, as a dict keyed by the key itself.

    One definition, because there were five hand-typed copies of this dict and every
    one of them named `flight_number`. They were built to be consumed by code that
    iterates `BOOKING_CURVE_KEYS` — `get_booking_curve_group_key`,
    `curve_identity_is_complete`, and one `candidate[key] != identity[key]`
    comparison — so when the per-flight component changed to `departure_time` on
    2026-09-03 each copy silently stopped supplying it. Measured consequence on the
    serving path: `curve_identity_is_complete` returned False for every request, so
    the 14 booking-curve features, the 5 volatility features and the 7 trend
    features all came back NaN even when the caller had resolved a departure time.
    The sixth copy, in `curve_window_definition`, raised `KeyError` instead.

    Alias resolution is on truthiness, which is what the `or` chains these copies
    used did. That is right for these columns — IATA codes and timestamps, where the
    only falsy values are None and the empty string, and both mean absent. It would
    be wrong for a numeric column, so this is not a general-purpose accessor.

    Missing components are returned as whatever `.get` gave (usually None) rather
    than omitted, so the result always has all five keys and a consumer indexing it
    by `BOOKING_CURVE_KEYS` cannot raise. Whether the identity is usable is
    `curve_identity_is_complete`'s question, and it is a separate one.
    """
    identity: Dict[str, Any] = {}
    for key in BOOKING_CURVE_KEYS:
        value = record.get(key)
        if not value:
            for alias in CURVE_KEY_ALIASES.get(key, ()):
                alt = record.get(alias)
                if alt:
                    value = alt
                    break
        identity[key] = value
    return identity


def curve_identity_mask(df: pd.DataFrame) -> pd.Series:
    """`curve_identity_is_complete` per row, indexed like `df`.
    False for every row when a key column is absent from the frame entirely: a
    column that is not there cannot identify anything, and the alternative —
    grouping on whichever subset happens to be present — is what
    `curve_group_columns` exists to stop a caller doing by hand.
    """
    if df.empty:
        return pd.Series(dtype="bool", index=df.index)
    missing = [k for k in BOOKING_CURVE_KEYS if k not in df.columns]
    if missing:
        return pd.Series(False, index=df.index)

    ok = pd.Series(True, index=df.index)
    for key in BOOKING_CURVE_KEYS:
        column = df[key]
        named = column.notna() & (
            column.astype("string").str.strip().fillna("") != "")
        ok &= named.fillna(False)
    return ok


def booking_horizon_days(
    df: pd.DataFrame,
    observed: Optional[pd.Series] = None,
) -> pd.Series:
    """Whole days from when each fare was observed to when its flight departs.

    One definition, called by every feature that needs a horizon:
    `days_until_departure` and `urgency` (temporal), `booking_curve_progress`
    (booking curve) and `average_booking_lead` (route aggregates). They were
    three separate calculations over two different sources, and they could
    disagree inside a single feature vector.

    `price_history.days_until_dep` is **not** consulted. That column is a
    denormalisation of exactly this subtraction, written at ingest, and it sits
    beside `day_of_week`, `month`, `week_of_year`, `is_holiday` and `is_weekend`
    — five more denormalisations of `departure_date` that the temporal features
    already ignore in favour of deriving them. Where the stored horizon disagrees
    with the pair it came from, the pair is what every other feature is computed
    against: the ordering timestamp defines each row's place on the timeline, so
    a horizon measured from anything else describes a different observation.
    Reading the column also produced a train/serve split, because the serving
    path had no column to read and derived the value from the request.

    Both sides are normalised to a date before subtracting, so the horizon is a
    whole number of days on the training and serving paths alike. A departure
    that precedes its own observation is not a horizon of zero and not a negative
    one; it is unreadable data, and comes back NaN — as does a row with no
    departure date or no usable observation time.

    `observed` lets a caller supply the observation times it has already
    resolved; the default is `ordering_timestamps(df)`.

    `departure_date` is parsed with `format="ISO8601", utc=True` for the reason
    `ordering_timestamps` records, and `utc=True` is what makes the format safe
    here: on a column mixing `"2026-08-20"` with `"2026-08-21T00:00:00Z"`,
    `format="ISO8601"` alone returns *object* dtype, and the `.dt` access two
    lines below would raise instead of returning a horizon. With `utc=True` the
    result is `datetime64[ns, UTC]` for every input shape measured — bare dates,
    timestamps, `date` objects, all-null and empty — and the tz is then stripped
    by the existing branch, so a naive input lands on exactly the value it did
    before. Measured on the mixed pair above: the horizon went from `[5.0, nan]`
    to `[5.0, 6.0]`.
    """
    if "departure_date" in df.columns:
        departs = pd.to_datetime(
            df["departure_date"], errors="coerce", utc=True, format="ISO8601")
    else:
        departs = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    seen = ordering_timestamps(df) if observed is None else observed

    if getattr(departs.dt, "tz", None) is not None:
        departs = departs.dt.tz_localize(None)
    if getattr(seen.dt, "tz", None) is not None:
        seen = seen.dt.tz_localize(None)

    horizon = (departs.dt.normalize() - seen.dt.normalize()).dt.days.astype("float64")
    return horizon.where(horizon >= 0)


def booking_horizon_from_dates(departure_date: Any, observed_at: Any) -> float:
    """`booking_horizon_days` for a single request, same rule and same result."""
    frame = pd.DataFrame({
        "departure_date": [departure_date],
        ORDERING_TIMESTAMP_KEY: [observed_at],
    })
    value = booking_horizon_days(frame).iloc[0]
    return float(value) if pd.notna(value) else float("nan")


def lag_tolerance_days(days_back: float) -> float:
    """How stale an observation may be and still count as the `days_back` lag."""
    return max(MIN_LAG_TOLERANCE_DAYS, float(days_back) * LAG_TOLERANCE_FRACTION)


def _price_at_offset(
    df: pd.DataFrame,
    offset_days: float,
    direction: str,
    *,
    price_col: str,
    group_cols: Optional[Sequence[str]],
) -> pd.Series:
    """The one as-of lookup along a booking curve, in either direction.

    `price_at_lag` and `price_at_horizon` are the two named wrappers. They share
    this body deliberately: a second, separately written copy of the join is the
    exact defect this module exists to prevent, and the backward and forward
    lookups differ only in the sign of the offset and the `direction` argument.

    Rows whose curve identity is incomplete take no part in the join, on either
    side. This is `curve_identity_is_complete`'s stated contract — "callers must
    treat False as 'this observation has no curve'" — and this function was the one
    caller that did not honour it. `pd.merge_asof(by=keys)` factorises the key
    columns, and a null factorises to a value that matches other nulls, so every
    unidentified observation on a route and date shared one curve: on a two-row
    frame with `departure_time` NULL, `attach_future_target` returned a label for
    the first row equal to the *second flight's* later fare. That is defect 1 of
    this module's header, reached through a populated-but-null column instead of
    through an absent one.

    It is not hypothetical and it is not historical. It is the state migration 001
    creates: the column arrives with no backfill, so all 32,709 pre-migration rows
    hold NULL and would have begun pooling the moment the migration was applied.
    The note above `BOOKING_CURVE_KEYS` claiming "nothing trains" without the
    column was true only of the missing-column case, which raises; the null case
    trained on cross-flight labels and reported nothing.
    """
    if df.empty or price_col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")

    keys = list(group_cols) if group_cols is not None else curve_group_columns(df)
    ts = ordering_timestamps(df)
    price = pd.to_numeric(df[price_col], errors="coerce")

    frame = pd.DataFrame({"_row": np.arange(len(df)), "_ts": ts.values,
                          "_price": price.values}, index=df.index)
    for k in keys:
        # Grouping on the raw value would treat "del" and "DEL" as two curves.
        frame[k] = df[k].astype(str).str.strip().str.upper() if df[k].dtype == object \
            else df[k]

    usable = frame["_ts"].notna() & pd.Series(
        curve_identity_mask(df).to_numpy(dtype=bool), index=df.index)
    if not usable.any():
        return pd.Series(np.nan, index=df.index, dtype="float64")

    # merge_asof requires each side globally sorted on its join key.
    right = frame.loc[usable & frame["_price"].notna(),
                      ["_ts", "_price", *keys]].sort_values("_ts")
    left = frame.loc[usable, ["_row", "_ts", *keys]].copy()
    left["_asof"] = left["_ts"] + pd.Timedelta(days=float(offset_days))
    left = left.sort_values("_asof")

    if right.empty:
        return pd.Series(np.nan, index=df.index, dtype="float64")

    merged = pd.merge_asof(
        left, right.rename(columns={"_ts": "_other_ts", "_price": "_other_price"}),
        left_on="_asof", right_on="_other_ts",
        by=keys or None, direction=direction,
        tolerance=pd.Timedelta(days=lag_tolerance_days(abs(float(offset_days)))),
    )

    out = np.full(len(df), np.nan, dtype="float64")
    out[merged["_row"].to_numpy()] = merged["_other_price"].to_numpy()
    return pd.Series(out, index=df.index, dtype="float64")


def price_at_lag(
    df: pd.DataFrame,
    days_back: float,
    *,
    price_col: str = "price",
    group_cols: Optional[Sequence[str]] = None,
) -> pd.Series:
    """Price on the same booking curve as observed `days_back` days earlier.

    An as-of (backward) join, not a positional shift: for each row observed at
    `t`, the most recent observation on the same curve at or before
    `t - days_back`, accepted only within `lag_tolerance_days(days_back)`.
    NaN where no such observation exists.

    Returned indexed like `df`, so the caller may assign it to a column of `df`
    regardless of how `df` happens to be sorted.
    """
    return _price_at_offset(df, -abs(float(days_back)), "backward",
                            price_col=price_col, group_cols=group_cols)


def price_at_horizon(
    df: pd.DataFrame,
    days_forward: float,
    *,
    price_col: str = "price",
    group_cols: Optional[Sequence[str]] = None,
) -> pd.Series:
    """Price on the same booking curve as observed `days_forward` days later.

    The supervised label, and the mirror image of `price_at_lag`: the *earliest*
    observation on the same curve at or after `t + days_forward`, accepted only
    within `lag_tolerance_days(days_forward)`. NaN where no such observation
    exists, which is how a row with no future to predict is excluded.

    Three properties matter, and the previous target joins had none of them:

    * The curve key is `BOOKING_CURVE_KEYS`, five columns, one of which pins the
      individual departure. Both former implementations joined on four keys —
      `training_dataset_builder` appended `flight_number` only inside
      `if "flight_number" in target_df.columns`, on a `target_df` built by a column
      selection that never included it, so the branch was dead and the label was
      some *other* flight's later fare. The fifth key was `flight_number` until the
      live provider was measured never to publish one; it is `departure_time` now,
      for the reason recorded above `BOOKING_CURVE_KEYS`.
    * A row whose key values do not identify a curve is not labelled at all.
      Naming the fifth key is not enough on its own: `merge_asof(by=...)` matches
      null to null, so before `_price_at_offset` applied `curve_identity_mask` a
      NULL `departure_time` reinstated exactly the cross-flight label this bullet
      claims to have closed.
    * The matched observation is strictly later than the row it labels, because
      `lag_tolerance_days(h) < h` for every `h >= MIN_TRAINABLE_HORIZON_DAYS`.
      The label therefore cannot be the row's own price, whatever the ingestion
      cadence — the leak is closed by arithmetic rather than by a check.
    """
    return _price_at_offset(df, abs(float(days_forward)), "forward",
                            price_col=price_col, group_cols=group_cols)


def attach_future_target(
    df: pd.DataFrame,
    horizon: int,
    *,
    price_col: str = "price",
    target_col: str = "target_price",
) -> pd.DataFrame:
    """`df` plus the supervised label for `horizon` days ahead, unlabelled rows dropped.

    The single definition of the training target. Both the dataset builder and
    `PriceModel._build_shifted_dataset` call this, so the frame the model trains
    on and the frame the target-leakage tests inspect are built by the same code.
    They were not: the builder joined on calendar-date equality keeping the first
    row of each day, while `_build_shifted_dataset` took that day's *minimum*
    fare, and only the second was ever tested.

    Raises on a horizon below `MIN_TRAINABLE_HORIZON_DAYS` instead of returning a
    frame, because there is no honest label to return.

    Also raises if the frame is missing any of `BOOKING_CURVE_KEYS`, rather than
    returning an all-NaN label. Both are honest — `_price_at_offset` refuses to
    join a frame it cannot key, so a four-key frame yields no labels either way —
    but an empty result reads as "no data", and the caller needs to hear "no
    fifth key". A frame without the departure-identifying key pools every flight
    on the route and date into one curve, so the label becomes some other
    aircraft's later fare. That is the defect this module was written for, and it
    survived because the old join's `flight_number` branch was guarded by an
    `if "flight_number" in ...` that was never true.
    """
    missing = [k for k in BOOKING_CURVE_KEYS if k not in df.columns]
    if missing:
        raise ValueError(
            f"cannot attach a supervised label: the frame is missing booking-curve "
            f"key column(s) {missing}. Without the full key "
            f"{BOOKING_CURVE_KEYS} the rows pooled into one curve are not one "
            f"flight's price history, and the label would be a different flight's "
            f"later fare."
        )
    h = int(horizon)
    if h < MIN_TRAINABLE_HORIZON_DAYS:
        raise ValueError(
            f"horizon {h} is not a trainable target: the label would be the "
            f"price on the same observation as the features, making every "
            f"price-derived feature a function of the target. Minimum trainable "
            f"horizon is {MIN_TRAINABLE_HORIZON_DAYS} day(s). Serve the observed "
            f"fare directly for the present-day point instead of predicting it."
        )
    if resolve_ordering_timestamp_column(df) is None:
        raise ValueError(
            f"cannot attach a supervised label: the frame has neither "
            f"'{ORDERING_TIMESTAMP_KEY}' nor '{FALLBACK_TIMESTAMP_KEY}', so there "
            f"is no observation time to measure {h} days forward from. An "
            f"unordered frame would yield an all-NaN label and an empty dataset, "
            f"which reads as 'no data' rather than 'no timestamps'."
        )
    # The columns being present is not the same as their being populated, and the
    # promise in the message above — that an unordered frame is reported as such
    # rather than as an empty dataset — was only kept for the column-level case.
    # A frame carrying both columns with every value NULL took the path below,
    # produced an all-NaN label, and returned zero rows with no explanation. That
    # is not hypothetical either: `search_timestamp` was added by migration 001
    # with no default and no backfill, so before `ordering_timestamps` coalesced
    # per row it was the state of the entire pre-migration corpus.
    if len(df) and ordering_timestamps(df).isna().all():
        raise ValueError(
            f"cannot attach a supervised label: all {len(df)} row(s) have an "
            f"unparseable or NULL observation time in both "
            f"'{ORDERING_TIMESTAMP_KEY}' and '{FALLBACK_TIMESTAMP_KEY}', so there "
            f"is nothing to measure {h} days forward from. This is a corpus "
            f"defect, not an absence of data — the rows exist and carry fares."
        )
    out = df.copy()
    out[target_col] = price_at_horizon(out, h, price_col=price_col)
    return out[out[target_col].notna()]


def price_changes_from_records(
    records: Optional[Sequence[Dict[str, Any]]],
    *,
    curve: Dict[str, Any],
    current_price: Optional[float],
    current_time: Any,
    lag_days: Sequence[int] = (1, 3),
) -> Dict[str, float]:
    """`price_change_{n}d` for a quoted fare, from raw `price_history` rows.

    The serve-side entry point for the day-based change features, so that a
    caller holding a list of history dicts does not have to reimplement the lag.
    It filters `records` to the one booking curve named by `curve`, appends the
    fare being quoted as the latest observation, and calls `price_at_lag` — the
    same function the training path calls.

    This replaces `flight_search_service`'s own version, which computed
    `flight.price - mean(prices observed in the last n days)` under the names
    `price_change_1d` and `price_change_3d`. A difference from a mean is not a
    difference from an earlier price: on a curve that rose steadily it reports
    roughly half the true change, and it was pooled across every airline and
    flight on the route because the history query filters on route and date only.
    Training meanwhile computed a per-flight positional shift. Two unrelated
    quantities, one pair of names, and the model's largest feature importance.

    Missing values are NaN, never 0.0. A route with no earlier observation of
    this flight has an unknown price change, and 0.0 would assert the fare had
    not moved.
    """
    empty = {f"price_change_{int(n)}d": float("nan") for n in lag_days}
    if current_price is None:
        return empty
    try:
        current = float(current_price)
    except (TypeError, ValueError):
        return empty
    if np.isnan(current):
        return empty

    target_key = get_booking_curve_group_key(curve)
    rows: List[Dict[str, Any]] = []
    for row in (records or []):
        if not isinstance(row, dict):
            continue
        candidate = {
            "origin_code": row.get("origin_code") or row.get("origin"),
            "destination_code": row.get("destination_code") or row.get("destination"),
            "airline_code": row.get("airline_code") or row.get("airline"),
            "flight_number": row.get("flight_number"),
            "departure_date": row.get("departure_date"),
        }
        if get_booking_curve_group_key(candidate) != target_key:
            continue
        ts = row.get(ORDERING_TIMESTAMP_KEY) or row.get(FALLBACK_TIMESTAMP_KEY)
        if ts is None or row.get("price") is None:
            continue
        rows.append({**candidate, ORDERING_TIMESTAMP_KEY: ts, "price": row["price"]})

    if not rows:
        return empty

    # The quoted fare is an observation on this curve and is known now, so it
    # belongs last. Appended after the history so its positional index is -1.
    rows.append({**{k: curve.get(k) for k in BOOKING_CURVE_KEYS},
                 ORDERING_TIMESTAMP_KEY: current_time, "price": current})
    df = pd.DataFrame(rows)

    changes: Dict[str, float] = {}
    for n in lag_days:
        prior = price_at_lag(df, int(n))
        val = prior.iloc[-1]
        changes[f"price_change_{int(n)}d"] = float(current - val) if pd.notna(val) else float("nan")
    return changes


def rolling_price_statistics(
    prices: Sequence[float],
    *,
    window: int = ROLLING_WINDOW_OBSERVATIONS,
) -> Dict[str, float]:
    """Window statistics over the most recent `window` prices, inclusive of the last.

    The single implementation both the training and the inference path call, so
    that "rolling standard deviation" cannot mean ddof=1 in one and ddof=0 in the
    other — which it did: training used pandas `.std()` and inference used
    `np.std()`, two different numbers under the same feature name.

    Including the current observation is deliberate and safe for a future-price
    target: the fare being quoted now is known at prediction time. It is *not*
    safe when the target is the current price, which is why horizon 0 is not a
    trainable horizon.
    """
    vals = pd.Series(list(prices), dtype="float64").dropna()
    if vals.empty:
        return {"mean": np.nan, "median": np.nan, "min": np.nan,
                "max": np.nan, "std": np.nan, "count": 0}
    tail = vals.iloc[-int(window):]
    return {
        "mean": float(tail.mean()),
        "median": float(tail.median()),
        "min": float(tail.min()),
        "max": float(tail.max()),
        # Undefined below two observations. Reported as NaN rather than 0.0,
        # which would assert that a single observation showed no variation.
        "std": float(tail.std(ddof=1)) if len(tail) >= MIN_OBSERVATIONS_FOR_STD else np.nan,
        "count": int(len(tail)),
    }


def booking_curve_progress(days_since_first: float, days_until_departure: Optional[float]) -> float:
    """How far along its selling window this observation sits, in [0, 1].

    Shared because the two former implementations disagreed: training divided by
    `(days_since + days_until).clip(lower=1.0)` and inference divided by the raw
    sum when positive. On a curve half a day old for a flight departing today
    that is 0.5 versus 1.0 under one feature name.
    """
    if days_since_first is None or (isinstance(days_since_first, float) and np.isnan(days_since_first)):
        return float("nan")
    if days_until_departure is None or (isinstance(days_until_departure, float)
                                       and np.isnan(days_until_departure)):
        return float("nan")
    span = float(days_since_first) + float(days_until_departure)
    if span <= 0:
        # Observed on the departure day itself, with no earlier observation: the
        # window has no measurable extent, so progress is 1.0 by definition
        # rather than 0.0 — the sale is over, not unstarted.
        return 1.0
    return float(min(1.0, max(0.0, float(days_since_first) / span)))


def curve_slope_acceleration(
    times: Sequence[Any],
    prices: Sequence[float],
) -> Dict[str, float]:
    """Slope and acceleration of the curve at its last point.

    Defined against the *immediately preceding observation* and the real elapsed
    time between them, which is what the shape of a curve at a point means. This
    is a positional lookback on purpose and is sound because the sequence is one
    booking curve in `ordering_timestamps` order; the audit's finding was about
    positional lookbacks *named* as day-based lags, which `price_at_lag` now
    handles instead.

    NaN — not 0.0 — when there is no preceding observation to measure against.
    """
    out = {"slope": float("nan"), "acceleration": float("nan")}
    ts = list(times)
    px = [None if p is None or (isinstance(p, float) and np.isnan(p)) else float(p)
          for p in prices]
    if len(ts) != len(px) or len(ts) < 2 or px[-1] is None or px[-2] is None:
        return out

    def _days(a: Any, b: Any) -> float:
        delta = pd.Timestamp(a) - pd.Timestamp(b)
        return float(delta.total_seconds()) / 86400.0

    dt_last = max(_days(ts[-1], ts[-2]), MIN_SLOPE_DELTA_DAYS)
    slope = (px[-1] - px[-2]) / dt_last
    out["slope"] = float(slope)

    if len(ts) >= 3 and px[-3] is not None:
        dt_prev = max(_days(ts[-2], ts[-3]), MIN_SLOPE_DELTA_DAYS)
        prev_slope = (px[-2] - px[-3]) / dt_prev
        out["acceleration"] = float((slope - prev_slope) / dt_last)
    return out


def get_booking_curve_group_key(record: Dict[str, Any]) -> Tuple[str, ...]:
    """The booking-curve identity of one record, as a tuple of strings.

    Derived from `BOOKING_CURVE_KEYS` rather than hand-typed. It used to be a
    literal five-element tuple naming each column, which is the defect this
    module's header describes — a second definition of the key, in the module
    that owns the first. When the per-flight component changed from
    `flight_number` to `departure_time` on 2026-09-03 this function kept reading
    `flight_number` and would have returned `""` in that slot for every record,
    so every one of a carrier's departures on a route and date produced the same
    key. Nothing would have raised; the curves would just have been wrong again.

    Case is normalised only for the columns that are codes. Uppercasing a
    timestamp or a date is meaningless, and doing it uniformly would hide the fact
    that the components are not all the same kind of thing.
    """
    parts: List[str] = []
    for key in BOOKING_CURVE_KEYS:
        value = str(record.get(key, "")).strip()
        parts.append(value.upper() if key in _CASE_NORMALISED_KEYS else value)
    return tuple(parts)


def sort_booking_curves_chronologically(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sorts observations chronologically by booking curve identifier and search_timestamp.
    Ensures complete chronological sequence before any target shift-join operations.
    """
    if df.empty:
        return df

    df_sorted = df.copy()

    # One resolver, so this function and the lag features cannot disagree about
    # which column means "earlier".
    df_sorted["_sort_ts"] = ordering_timestamps(df_sorted)

    sort_cols = curve_group_columns(df_sorted) + ["_sort_ts"]
    df_sorted = df_sorted.sort_values(by=sort_cols, ascending=True).reset_index(drop=True)
    
    if "_sort_ts" in df_sorted.columns:
        df_sorted = df_sorted.drop(columns=["_sort_ts"])

    return df_sorted


def deduplicate_session_aware(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicates observations within a single search session while preserving
    legitimate longitudinal observations collected across separate search sessions.
    """
    if df.empty:
        return df

    dedup_cols = curve_group_columns(df)

    if "search_session_id" in df.columns and df["search_session_id"].notna().any():
        dedup_cols.append("search_session_id")
    elif ORDERING_TIMESTAMP_KEY in df.columns:
        dedup_cols.append(ORDERING_TIMESTAMP_KEY)
    elif FALLBACK_TIMESTAMP_KEY in df.columns:
        dedup_cols.append(FALLBACK_TIMESTAMP_KEY)

    return df.drop_duplicates(subset=dedup_cols, keep="first").reset_index(drop=True)


# ── The write side of the same rule ────────────────────────────────────────────
#
# `deduplicate_session_aware` above is the read-side twin of what follows, and the
# two are meant to be read together. That one collapses duplicates already in the
# corpus when a training frame is built; these refuse to store them in the first
# place. Neither substitutes for the other — the read side cannot stop a duplicate
# from being written, and the write side cannot repair the rows already there.
#
# Why the write side exists at all. Migration 001 STEP 8b creates
# `ux_price_history_observation`, unique on
#   (search_session_id, origin_code, destination_code, airline_code,
#    departure_time, departure_date, COALESCE(cabin_class, ''))
# where `search_session_id` and `departure_time` are both non-NULL. PostgREST
# submits `insert(list_of_rows)` as one statement, so once that index exists a
# single duplicated provider card **rejects the whole route's batch** — twenty good
# observations lost because the scraper listed one flight twice. STEP 8's own
# PRECONDITION names this as the gate on running 8b.
#
# The key is two components wider than `BOOKING_CURVE_KEYS`. `search_session_id`,
# because two observations of the same flight in *different* searches are the
# longitudinal signal this project is built on and must never be collapsed — that
# is the difference between de-duplication and destroying the corpus. And
# `cabin_class`, because the index includes it. `cabin_class` is also the one place
# these two functions and their read-side twin disagree: `deduplicate_session_aware`
# omits it, which is harmless only because `cabin_class` is a search *parameter* and
# is therefore constant across every row of a session. A future writer that varies
# it within one session would have the read side collapse two cabins the database
# deliberately kept apart.
OBSERVATION_IDENTITY_KEYS: Tuple[str, ...] = (
    "search_session_id", *BOOKING_CURVE_KEYS, "cabin_class",
)


def observation_identity_key(record: Dict[str, Any]) -> Optional[Tuple[str, ...]]:
    """The identity STEP 8b's index gives one row, or None if it gives it none.

    None means the row falls outside the index's partial predicate — it carries no
    `search_session_id`, or no `departure_time` — so the database cannot reject it
    as a duplicate and this module must not drop it either. Two such rows being
    "the same observation" is a data judgement the index does not make, and
    discarding one of them would be precisely the silent loss the rest of this file
    exists to prevent. Note that `MarketDataController.get_db_payload` strips keys
    whose value is None, so an absent key and a NULL one arrive here identically
    and are treated the same; this function reads with `.get` for that reason.

    Case: `get_booking_curve_group_key` upper-cases the three IATA components
    because it must agree with the training-side grouping, while Postgres compares
    them exactly. That makes this key marginally *coarser* than the index for those
    columns, which is the safe direction — it can never let a collision through,
    only merge two rows Postgres would have kept apart, and the sole way that
    happens is a case difference in an airline or airport code, which is the same
    flight either way. `format_payload` upper-cases all three before they get here,
    so it cannot arise on the live path. `cabin_class` is compared exactly, as the
    index does.
    """
    session = record.get("search_session_id")
    if session is None or str(session).strip() == "":
        return None
    # Checked by name rather than by position in the curve key: the per-flight
    # component moved from `flight_number` to `departure_time` on 2026-09-03, and a
    # positional read would have kept passing after that change while testing the
    # wrong column.
    departure_time = record.get("departure_time")
    if departure_time is None or str(departure_time).strip() == "":
        return None
    return (
        str(session).strip(),
        *get_booking_curve_group_key(record),
        str(record.get("cabin_class") or "").strip(),
    )


def _observation_price(record: Dict[str, Any]) -> float:
    """The row's fare as a float, or +inf when it does not carry a usable one.

    +inf rather than 0.0: this value only ever decides which of two otherwise
    identical rows survives, and a row whose fare cannot be read must *lose* that
    comparison to one whose fare can. 0.0 would make it win every time and quietly
    select the unusable row. NaN would give the right answer by accident — every
    `<` against it is False — which is not a property to rely on.
    """
    value = record.get("price")
    if value is None:
        return float("inf")
    try:
        price = float(value)
    except (TypeError, ValueError):
        return float("inf")
    if price != price:  # NaN
        return float("inf")
    return price


def deduplicate_observation_batch(
    records: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Collapse rows of one batch that would collide in `ux_price_history_observation`.

    Returns the rows to submit — in the order their identity first appeared, so a
    caller that logs or samples the batch sees the provider's own ordering — and a
    report of what was collapsed. The report is the point as much as the filtering
    is: a provider that lists the same flight twice is a fact about the scraper that
    nothing in this project currently measures, and `dropped` is that measurement.

    One row survives per identity, and it is the one with the **lowest price**. That
    choice is not arbitrary in two ways. It matches `attach_future_target`, which
    takes the minimum when several observations sit at the same point of a curve, so
    the row stored and the label derived from a later batch follow one convention.
    And it is deterministic: provider ordering varies between runs, so "keep the
    first" would make the stored corpus depend on the order the scraper happened to
    emit cards in. Ties keep the earlier row, which makes the function stable.

    Sufficiency, stated because it is what makes this cheap fix a complete one.
    This guards *within* a batch only, and that is enough for 8b because
    `search_session_id` is minted once per `FlightSearchService.search()` call
    (`flight_search_service.py:339`) and each call performs exactly one insert, with
    no retry — so no two batches can ever share a session id, and cross-batch
    collisions on this key are unreachable rather than merely unlikely. If a caller
    ever reuses a session id across inserts, or retries a failed batch under the
    same one, this function stops being sufficient and STEP 8's other option — an
    upsert with `ignore_duplicates=True` — becomes necessary.

    One residual, which is why STEP 8b's note also asks for the upsert. The key
    compares `departure_time` as the string being submitted, while the database
    compares it as a timestamp. A naive `2026-07-23T06:00:00` and an offset-bearing
    form of the same instant are two strings here and could be one value there,
    depending on the column's type and the session timezone. `normalize_departure_time`
    emits one shape per provider response, so a mixed batch is not something today's
    scraper produces — but the guarantee is about shapes, not about today's scraper,
    so the upsert is what closes it. Do not add the upsert before 8b exists:
    `on_conflict` requires the index, and PostgREST fails the insert without it.
    """
    kept: List[Dict[str, Any]] = []
    position: Dict[Tuple[str, ...], int] = {}
    best: Dict[Tuple[str, ...], float] = {}
    seen: Dict[Tuple[str, ...], List[float]] = {}
    unindexable = 0

    for record in records:
        key = observation_identity_key(record)
        if key is None:
            # Outside the index's predicate: the database will accept it, so this
            # function passes it through rather than deciding it is a duplicate.
            unindexable += 1
            kept.append(record)
            continue

        price = _observation_price(record)
        if key not in position:
            position[key] = len(kept)
            best[key] = price
            seen[key] = [price]
            kept.append(record)
            continue

        seen[key].append(price)
        if price < best[key]:
            kept[position[key]] = record
            best[key] = price

    collapsed = {k: v for k, v in seen.items() if len(v) > 1}
    spreads = []
    for prices in collapsed.values():
        finite = [p for p in prices if p != float("inf")]
        if len(finite) > 1:
            spreads.append(max(finite) - min(finite))

    report: Dict[str, Any] = {
        "submitted": len(records),
        "kept": len(kept),
        "dropped": len(records) - len(kept),
        "groups_collapsed": len(collapsed),
        # A collapsed group whose members disagree on price is the interesting case:
        # the provider listed one flight at two fares, so the corpus was about to
        # record two different "the" prices for the same observation. Same-price
        # duplicates are a repeated card and cost nothing but a row.
        "groups_disagreeing_on_price": sum(1 for s in spreads if s > 0.0),
        "max_price_spread": max(spreads) if spreads else 0.0,
        # Rows the index does not cover, reported rather than silently lumped in
        # with the survivors: they are exactly the rows that carry no
        # `departure_time`, which is to say the rows that can never be labelled.
        "unindexable": unindexable,
    }
    return kept, report
