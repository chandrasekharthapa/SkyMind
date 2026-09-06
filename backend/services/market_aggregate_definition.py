"""Route- and airline-level market aggregates, defined once for both paths.

Every quantity here used to be a `groupby(route).transform(...)` over the whole
training corpus. That is a leak, and a large one: the aggregate a row received
was computed from observations recorded *after* that row, including the very
observation the row is supervised against. `historical_maximum_fare` could
literally equal the label, and `historical_average_fare` was the mean of a window
that contained it.

Nothing detected it. `booking_curve_validator.validate_target_leakage` recomputes
features on a timeline-masked frame and compares — the right test — but its
comparison list named ten lag and rolling features and none of these fourteen.
The training/inference parity test used a single row, and every group aggregate
over a one-row group degenerates to that row's own price, so both branches agreed
on a number that was wrong in the same way.

The rule this module enforces: **a feature for an observation recorded at time t
is computed from the observations recorded at or before t, and from nothing
else.** Rows sharing a timestamp all see the window that closes after the last of
them, so no statistic depends on the order of rows recorded at the same instant.
That is also exactly what the leakage validator computes when it masks everything
after t, which is why the validator can now prove this rather than assume it.

Including the row's own observation is deliberate and safe here for the same
reason it is safe in `rolling_price_statistics`: the fare being quoted now is
known at prediction time. It is not safe when the target is the current price,
which is why horizon 0 is not a trainable horizon.

The serve-side entry points build a frame from the history records, append the
fare being quoted as the latest observation, and call the same functions the
training path calls. Parity is by construction, not by a second implementation
that has to be kept in step — the failure mode this repository already had five
times over under identical feature names.

Nothing here fills a missing value. The previous version filled a single
observation's standard deviation with 0.0 ("no variation"), an unknown route
share with 0.0, and — when the route or airline columns were absent — reported
`airline_market_share` as 1.0, `airline_price_rank` as 1.0 and
`airline_average_fare` as the row's own price. XGBoost consumes NaN natively.
"""

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from backend.services.booking_curve_definition import (
    FALLBACK_TIMESTAMP_KEY,
    MIN_OBSERVATIONS_FOR_STD,
    ORDERING_TIMESTAMP_KEY,
    booking_horizon_days,
    ordering_timestamps,
)

# The route a fare belongs to, and the airline flying it. Deliberately not the
# five-part booking-curve key: these features are about the market around an
# observation, not about one flight's price history.
ROUTE_GROUP_KEYS: List[str] = ["origin_code", "destination_code"]
AIRLINE_KEY: str = "airline_code"

# Sample standard deviation, matching `rolling_price_statistics`. The repository
# had pandas `.std()` (ddof=1) on one path and `np.std()` (ddof=0) on the other
# under one name; the point of a shared definition is that it cannot.
STD_DDOF: int = 1

ROUTE_FEATURES: List[str] = [
    "historical_average_fare", "historical_median_fare", "historical_minimum_fare",
    "historical_maximum_fare", "historical_price_std", "airline_count",
    "average_booking_lead", "observation_density",
]

AIRLINE_FEATURES: List[str] = [
    "airline_average_fare", "airline_market_share", "airline_route_share",
    "airline_price_rank", "airline_volatility", "airline_observation_count",
]


def route_group_columns(df: pd.DataFrame) -> List[str]:
    """The route key columns actually present on `df`."""
    return [k for k in ROUTE_GROUP_KEYS if k in df.columns]


def _require_route_identity(df: pd.DataFrame) -> List[str]:
    keys = route_group_columns(df)
    if not keys:
        raise ValueError(
            "market aggregates need a route identity: none of "
            f"{ROUTE_GROUP_KEYS} is present on a frame with columns "
            f"{sorted(df.columns)[:12]}. Without one, every observation would be "
            "pooled into a single market and each route's statistics would be "
            "the whole corpus's."
        )
    return keys


def _numeric(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce")


def _nan(df: pd.DataFrame) -> pd.Series:
    return pd.Series(np.nan, index=df.index, dtype="float64")

def _as_of(values: pd.Series, times: pd.Series, keys: Optional[pd.DataFrame],
           run) -> pd.Series:
    """Apply a cumulative statistic within each group, in observation order.

    `run` receives one group's values, sorted by observation time with unusable
    timestamps dropped, and returns a same-length sequence whose i-th element is
    the statistic over elements 0..i.

    Two properties make this the right shape rather than
    `groupby(...).transform(stat)`:

    * **Tie collapse.** Every row sharing a timestamp takes the value computed
      after the last of them, so no statistic depends on the order of rows
      recorded at the same instant — and the result is what a frame masked to
      `recorded_at <= t` produces, which is what the leakage validator compares
      against.
    * **Unorderable rows abstain.** A row whose timestamp will not parse gets
      NaN and contributes to nobody else's window. Substituting row position for
      a missing timestamp is how a frame sorted by insertion order comes to look
      chronological.
    """
    frame = pd.DataFrame({"_v": values, "_t": times})
    if keys is None or keys.shape[1] == 0:
        groups: Any = [(None, frame)]
    else:
        frame = frame.join(keys)
        groups = frame.groupby(list(keys.columns), sort=False, dropna=False)

    out = pd.Series(np.nan, index=frame.index, dtype="float64")
    for _, grp in groups:
        grp = grp[grp["_t"].notna()].sort_values("_t", kind="mergesort")
        if grp.empty:
            continue
        running = pd.Series(np.asarray(run(grp["_v"]), dtype="float64"),
                            index=grp.index)
        # `transform("last")` over the timestamp, on an already-sorted group.
        out.loc[grp.index] = running.groupby(
            grp["_t"].to_numpy(), sort=False).transform("last")
    return out


def as_of_stat(values: pd.Series, times: pd.Series,
               keys: Optional[pd.DataFrame], stat: str) -> pd.Series:
    """`stat` over every observation in the same group at or before each row's time."""
    numeric = pd.to_numeric(values, errors="coerce")
    if stat == "std":
        # Undefined below two observations, and reported as NaN rather than 0.0,
        # which would assert that a single observation showed no variation.
        def run(s: pd.Series) -> pd.Series:
            return s.expanding(min_periods=MIN_OBSERVATIONS_FOR_STD).std(ddof=STD_DDOF)
    elif stat in ("mean", "median", "min", "max", "count"):
        def run(s: pd.Series) -> pd.Series:
            return getattr(s.expanding(min_periods=1), stat)()
    else:
        raise ValueError(f"unsupported as-of statistic: {stat!r}")
    return _as_of(numeric, times, keys, run)


def as_of_distinct_count(values: pd.Series, times: pd.Series,
                         keys: Optional[pd.DataFrame]) -> pd.Series:
    """How many distinct non-null values the group has shown at or before each row."""
    def run(s: pd.Series) -> pd.Series:
        return (s.notna() & ~s.duplicated()).cumsum()
    return _as_of(pd.Series(values), times, keys, run)

def as_of_price_rank(df: pd.DataFrame, route_keys: List[str], times: pd.Series,
                     airline_mean: pd.Series) -> pd.Series:
    """Where this airline's fare-so-far ranks among the airlines on its route.

    1 is the cheapest. The comparison set is every airline observed on the route
    at or before this row's timestamp, each represented by its own as-of mean
    fare — so an airline that has not been seen yet does not rank, and no
    airline's rank is decided by fares quoted after the row being ranked.

    The old version ranked whole-corpus means and mapped them back with
    `pd.merge`, which returns a fresh `RangeIndex`. The caller assigns the result
    into a frame built with the *input* frame's index, so on any frame whose index
    is not `0..n-1` — which includes every training frame, because
    `attach_future_target` drops the rows it cannot label — the ranks landed on
    the wrong rows. It was not detectable from the values: a rank column of
    plausible small integers, silently permuted. This returns a Series indexed
    like `df` by construction.
    """
    work = pd.DataFrame({"_t": times, "_a": df[AIRLINE_KEY], "_m": airline_mean})
    for col in route_keys:
        work[col] = df[col]
    usable = work[work["_t"].notna() & work["_a"].notna() & work["_m"].notna()]
    if usable.empty:
        return _nan(df)

    pieces: List[pd.DataFrame] = []
    for _, grp in usable.groupby(route_keys, sort=False, dropna=False):
        # One row per (timestamp, airline): the airline's as-of mean at that
        # instant. Forward-filled across the route's other timestamps, so an
        # airline that quoted nothing at t is still ranked on what it last quoted.
        table = (grp.groupby(["_t", "_a"], sort=True, dropna=False)["_m"]
                    .last().unstack("_a").sort_index().ffill())
        ranks = table.rank(axis=1, ascending=True)
        long = ranks.reset_index().melt(id_vars="_t", var_name="_a",
                                        value_name="_rank")
        long = long[long["_rank"].notna()]
        for col in route_keys:
            long[col] = grp[col].iloc[0]
        pieces.append(long)

    lookup = pd.concat(pieces, ignore_index=True).set_index(
        route_keys + ["_a", "_t"])["_rank"]
    if lookup.index.has_duplicates:
        raise ValueError(
            "as-of price rank produced two ranks for one "
            "(route, airline, timestamp); the aggregation above should make that "
            "impossible, so the grouping keys have drifted."
        )
    # A tz-aware timestamp level must stay tz-aware: `times.to_numpy()` would
    # hand over UTC-naive values, the lookup would match nothing, and every rank
    # would come back NaN with no error anywhere.
    wanted = pd.MultiIndex.from_arrays(
        [df[col] for col in route_keys] + [df[AIRLINE_KEY], times])
    return pd.Series(lookup.reindex(wanted).to_numpy(), index=df.index,
                     dtype="float64")

def _require_unique_index(df: pd.DataFrame, who: str) -> None:
    if df.index.has_duplicates:
        # The returned Series are aligned back onto the caller's frame by index
        # label. A duplicated label makes that alignment ambiguous, so refuse
        # rather than emit a silently mispaired feature column.
        raise ValueError(
            f"{who} requires a unique index: features are aligned back to the "
            "caller's frame by index label."
        )


def route_aggregates(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """The eight route features, one value per row, each as of that row's time."""
    _require_unique_index(df, "route_aggregates")
    keys = _require_route_identity(df)
    times = ordering_timestamps(df)
    route = df[keys]
    price = _numeric(df, "price")

    return {
        "historical_average_fare": as_of_stat(price, times, route, "mean"),
        "historical_median_fare": as_of_stat(price, times, route, "median"),
        "historical_minimum_fare": as_of_stat(price, times, route, "min"),
        "historical_maximum_fare": as_of_stat(price, times, route, "max"),
        "historical_price_std": as_of_stat(price, times, route, "std"),
        "airline_count": (
            as_of_distinct_count(df[AIRLINE_KEY], times, route)
            if AIRLINE_KEY in df.columns else _nan(df)
        ),
        "average_booking_lead": as_of_stat(
            booking_horizon_days(df, observed=times), times, route, "mean"),
        "observation_density": as_of_stat(price, times, route, "count"),
    }


def airline_aggregates(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """The six airline features, one value per row, each as of that row's time."""
    _require_unique_index(df, "airline_aggregates")
    keys = _require_route_identity(df)
    if AIRLINE_KEY not in df.columns:
        # Unknowable, so reported as unknown. The previous version answered
        # 1.0 for market share, 1.0 for route share, 1.0 for rank, 0.0 for
        # volatility and the row's own price for the airline average.
        return {name: _nan(df) for name in AIRLINE_FEATURES}

    times = ordering_timestamps(df)
    route = df[keys]
    airline = df[keys + [AIRLINE_KEY]]
    price = _numeric(df, "price")

    mean_fare = as_of_stat(price, times, airline, "mean")
    airline_obs = as_of_stat(price, times, airline, "count")
    route_obs = as_of_stat(price, times, route, "count")

    # Distinct routes this airline has been seen on, over distinct routes anyone
    # has been seen on — both as of this row's time. The denominator is corpus
    # wide on purpose: it is the size of the market, not of the route.
    pair = df[keys].astype("string").agg("→".join, axis=1)
    airline_routes = as_of_distinct_count(pair, times, df[[AIRLINE_KEY]])
    market_routes = as_of_distinct_count(pair, times, None)

    out = {
        "airline_average_fare": mean_fare,
        "airline_market_share": airline_obs / route_obs.where(route_obs > 0),
        "airline_route_share": airline_routes / market_routes.where(market_routes > 0),
        "airline_price_rank": as_of_price_rank(df, keys, times, mean_fare),
        "airline_volatility": as_of_stat(price, times, airline, "std"),
        "airline_observation_count": airline_obs,
    }
    # Every feature here describes *this row's airline*, so a row that does not
    # name one has none of them. `_as_of` groups with `dropna=False`, which is
    # right for the window semantics and wrong for identity: without this mask a
    # null airline forms its own group and is credited with a route share — a
    # request that named no carrier came back with `airline_route_share` 1.0,
    # "this airline flies every route in the market".
    named = df[AIRLINE_KEY].notna()
    if not named.all():
        out = {name: series.where(named) for name, series in out.items()}
    return out

def _observation_frame(
    records: Optional[Sequence[Dict[str, Any]]],
    *,
    query: Dict[str, Any],
    current_price: Optional[float],
    current_time: Any,
) -> Optional[pd.DataFrame]:
    """History rows plus the fare being quoted, as a frame the training path accepts.

    Records are *not* filtered to the requested route. These features are about
    the market around an observation: the rank needs the other airlines on the
    route, and the route-share denominator is the whole market's route count.

    An unusable quoted price is not fatal here, and that is a deliberate
    difference from `price_changes_from_records`, which returns all-NaN in the
    same situation. `price_change_1d` *is* `current - prior`: with no current
    price there is nothing to compute. A market aggregate is a statistic over a
    window that the quote merely joins, so with no usable quote the window is
    still well defined — it is the market as of the request time. The row is
    appended anyway, carrying the route, airline and timestamp but no price, so
    the request still has a row to be read back from and still counts toward the
    distinct-airline and distinct-route tallies. `expanding` skips the NaN, so
    every price statistic is the history's, and `observation_density` counts the
    history only.
    """
    try:
        price = float(current_price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        price = float("nan")

    rows: List[Dict[str, Any]] = []
    for row in (records or []):
        if not isinstance(row, dict):
            continue
        ts = row.get(ORDERING_TIMESTAMP_KEY) or row.get(FALLBACK_TIMESTAMP_KEY)
        if ts is None or row.get("price") is None:
            continue
        origin = row.get("origin_code") or row.get("origin")
        destination = row.get("destination_code") or row.get("destination")
        if not origin or not destination:
            continue
        rows.append({
            "origin_code": origin,
            "destination_code": destination,
            AIRLINE_KEY: row.get(AIRLINE_KEY) or row.get("airline"),
            # `average_booking_lead` derives the horizon from this pair rather
            # than reading a stored `days_until_dep`, so the departure date has
            # to travel with the observation.
            "departure_date": row.get("departure_date"),
            ORDERING_TIMESTAMP_KEY: ts,
            "price": row.get("price"),
        })

    origin = query.get("origin_code") or query.get("origin")
    destination = query.get("destination_code") or query.get("destination")
    if not origin or not destination:
        return None

    # The fare being quoted is an observation, and it is known now, so it belongs
    # in the window its own features are computed over — the same argument
    # `rolling_price_statistics` makes. Appended last and read back by index
    # label, never by position. `price` is NaN when no usable fare was supplied.
    rows.append({
        "origin_code": origin,
        "destination_code": destination,
        AIRLINE_KEY: query.get(AIRLINE_KEY) or query.get("airline"),
        "departure_date": query.get("departure_date"),
        ORDERING_TIMESTAMP_KEY: current_time,
        "price": price,
    })
    return pd.DataFrame(rows)

def _quoted_row(
    build,
    names: Sequence[str],
    records: Optional[Sequence[Dict[str, Any]]],
    query: Dict[str, Any],
    current_price: Optional[float],
    current_time: Any,
) -> Dict[str, float]:
    frame = _observation_frame(records, query=query, current_price=current_price,
                              current_time=current_time)
    if frame is None or frame.empty:
        return {name: float("nan") for name in names}
    request = frame.index[-1]
    columns = build(frame)
    out: Dict[str, float] = {}
    for name in names:
        value = columns[name].loc[request]
        out[name] = float(value) if pd.notna(value) else float("nan")
    return out


def route_aggregates_from_records(
    records: Optional[Sequence[Dict[str, Any]]],
    *,
    query: Dict[str, Any],
    current_price: Optional[float],
    current_time: Any,
) -> Dict[str, float]:
    """The eight route features for a fare being quoted now, from raw history rows.

    Calls `route_aggregates` — the function the training path calls — on a frame
    ending in the quoted fare, and returns that row. There is no second
    implementation to keep in step.
    """
    return _quoted_row(route_aggregates, ROUTE_FEATURES, records, query,
                       current_price, current_time)


def airline_aggregates_from_records(
    records: Optional[Sequence[Dict[str, Any]]],
    *,
    query: Dict[str, Any],
    current_price: Optional[float],
    current_time: Any,
) -> Dict[str, float]:
    """The six airline features for a fare being quoted now, from raw history rows."""
    return _quoted_row(airline_aggregates, AIRLINE_FEATURES, records, query,
                       current_price, current_time)


# ---------------------------------------------------------------------------
# Snapshot features: one route, one search.
#
# These are cross-sectional, not as-of. At serve time a snapshot is the set of
# flights one live search returned for one route, so the training analogue is the
# set of observations sharing a route *and an ordering timestamp*. That group is
# mask-invariant by construction: every member carries the timestamp the label row
# carries, so masking the corpus to `<= t` cannot remove one of them.
#
# It was keyed on `recorded_at` while the pipeline orders on `search_timestamp`.
# Where those agree the group is a single search and nothing leaks. Where they do
# not — a nightly batch stamping one `recorded_at` on rows searched hours apart,
# which is what the ingest actually does — the group spans searches and the
# statistics read fares quoted after the row. Measured on a batch-written
# fixture: eight of the twelve leaked, `lowest_fare` 4588 -> 6727
# and `total_live_flights` 2 -> 1 once the corpus was masked. Keying on the
# resolved ordering column removes the failure mode rather than testing for it.
# ---------------------------------------------------------------------------

SNAPSHOT_FEATURES: List[str] = [
    "lowest_fare", "highest_fare", "average_fare", "median_fare", "fare_spread",
    "price_std_dev", "total_live_flights", "direct_ratio", "connecting_ratio",
    "airline_diversity", "snapshot_quality", "snapshot_completeness",
]

# Fewer than this many priced flights and the quality score is discounted. Kept
# here so `MarketSnapshotProvider` and the training path cannot drift apart.
QUALITY_SPARSE_PRICE_COUNT: int = 3
QUALITY_SPARSE_PENALTY: float = 0.9
QUALITY_INCOMPLETE_THRESHOLD: float = 0.8
QUALITY_INCOMPLETE_PENALTY: float = 0.8


def snapshot_completeness_score(total_flights: float, priced_flights: float) -> float:
    """Share of the flights in a snapshot that carried a usable fare."""
    if not total_flights or pd.isna(total_flights) or float(total_flights) <= 0:
        return float("nan")
    return float(priced_flights) / float(total_flights)


def snapshot_quality_score(
    total_flights: float, priced_flights: float, search_success: bool = True
) -> float:
    """The snapshot's own quality score, from its size and its completeness.

    One definition for both paths. `MarketSnapshotProvider` computed this at serve
    time while the training path hardcoded 1.0 for every row, so the model was
    trained to believe the feature is a constant and then shown 0.72 in
    production. A training row exists because a search returned it, so
    `search_success` is True on that side; everything else is recomputable.
    """
    completeness = snapshot_completeness_score(total_flights, priced_flights)
    if pd.isna(completeness):
        return float("nan")
    quality = 1.0 if search_success else 0.0
    if completeness < QUALITY_INCOMPLETE_THRESHOLD:
        quality *= QUALITY_INCOMPLETE_PENALTY
    if float(priced_flights) < QUALITY_SPARSE_PRICE_COUNT:
        quality *= QUALITY_SPARSE_PENALTY
    return round(quality, 2)


def stop_ratios(direct_count: float, connecting_count: float) -> Dict[str, float]:
    """Direct and connecting share of the flights whose stop count is *known*.

    The denominator is deliberately not the snapshot size. A flight with no
    segment data has an unknown stop count, and both paths used to resolve that
    unknown to "direct" — the provider because `stops` defaults to 0 before the
    itinerary check, the training branch because a missing `stops` column reported
    `direct_ratio` 1.0 and `connecting_ratio` 0.0. Unknown stops now leave the
    ratios undefined instead of inventing a non-stop flight.
    """
    known = float(direct_count) + float(connecting_count)
    if known <= 0:
        return {"direct_ratio": float("nan"), "connecting_ratio": float("nan")}
    return {"direct_ratio": float(direct_count) / known,
            "connecting_ratio": float(connecting_count) / known}


def snapshot_group_columns(df: pd.DataFrame) -> List[str]:
    """The columns identifying one search: the route plus the ordering timestamp."""
    return _require_route_identity(df) + ["_snapshot_ts"]


def snapshot_aggregates(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """The twelve snapshot features for every row of a training frame.

    Grouped by route and ordering timestamp, so each group is one search. Rows
    whose timestamp will not parse are their own group of one and abstain rather
    than pooling together under a shared NaT key.
    """
    _require_unique_index(df, "snapshot_aggregates")
    route_keys = _require_route_identity(df)
    if df.empty:
        return {name: pd.Series(dtype="float64") for name in SNAPSHOT_FEATURES}

    times = ordering_timestamps(df)
    price = _numeric(df, "price")
    frame = df.assign(_snapshot_ts=times, _snapshot_price=price)
    # A NaT key would collapse every unorderable row into one snapshot. Give each
    # its own key instead, so it can only ever describe itself.
    unorderable = times.isna()
    if unorderable.any():
        frame.loc[unorderable, "_snapshot_ts"] = [
            pd.Timestamp("1677-09-22", tz="UTC") + pd.Timedelta(seconds=int(i))
            for i in range(int(unorderable.sum()))
        ]
    group = frame.groupby(route_keys + ["_snapshot_ts"], dropna=False)["_snapshot_price"]

    lowest = group.transform("min")
    highest = group.transform("max")
    priced = group.transform("count").astype("float64")
    size = group.transform("size").astype("float64")
    # `transform("std", ddof=...)` rather than a lambda: pandas returns NaN for a
    # one-member group without numpy warning about the degrees of freedom.
    std = group.transform("std", ddof=STD_DDOF)
    std = std.where(priced >= MIN_OBSERVATIONS_FOR_STD)

    out: Dict[str, pd.Series] = {
        "lowest_fare": lowest,
        "highest_fare": highest,
        "average_fare": group.transform("mean"),
        "median_fare": group.transform("median"),
        "fare_spread": highest - lowest,
        "price_std_dev": std,
        "total_live_flights": size,
    }

    if "stops" in df.columns:
        stops = _numeric(df, "stops")
        by_group = frame.assign(_stops=stops).groupby(
            route_keys + ["_snapshot_ts"], dropna=False)["_stops"]
        directs = by_group.transform(lambda s: (s == 0).sum()).astype("float64")
        connectings = by_group.transform(lambda s: (s > 0).sum()).astype("float64")
        known = directs + connectings
        out["direct_ratio"] = (directs / known).where(known > 0)
        out["connecting_ratio"] = (connectings / known).where(known > 0)
    else:
        out["direct_ratio"] = _nan(df)
        out["connecting_ratio"] = _nan(df)

    if AIRLINE_KEY in df.columns:
        out["airline_diversity"] = frame.groupby(
            route_keys + ["_snapshot_ts"], dropna=False
        )[AIRLINE_KEY].transform("nunique").astype("float64")
    else:
        out["airline_diversity"] = _nan(df)

    completeness = (priced / size).where(size > 0)
    quality = pd.Series(1.0, index=df.index, dtype="float64")
    quality = quality.where(completeness >= QUALITY_INCOMPLETE_THRESHOLD,
                            quality * QUALITY_INCOMPLETE_PENALTY)
    quality = quality.where(priced >= QUALITY_SPARSE_PRICE_COUNT,
                            quality * QUALITY_SPARSE_PENALTY)
    out["snapshot_quality"] = quality.where(completeness.notna()).round(2)
    out["snapshot_completeness"] = completeness

    for name in SNAPSHOT_FEATURES:
        out[name] = pd.Series(out[name], index=df.index, dtype="float64")
    return out


def snapshot_aggregates_from_snapshot(snapshot: Any) -> Dict[str, float]:
    """The twelve snapshot features from a live `MarketSnapshot` (or its dict).

    Reads the statistics the provider already computed rather than recomputing
    them, and derives the three it does not carry — the two stop ratios and the
    airline diversity — through the same functions the training path uses. The
    provider is responsible for computing `price_std_dev`, `snapshot_quality` and
    `snapshot_completeness` by this module's definitions; `MarketSnapshotProvider`
    calls into here for exactly that reason.
    """
    if snapshot is None:
        return {name: float("nan") for name in SNAPSHOT_FEATURES}

    def field(name: str, default: Any = None) -> Any:
        if isinstance(snapshot, dict):
            return snapshot.get(name, default)
        return getattr(snapshot, name, default)

    def number(name: str) -> float:
        try:
            value = float(field(name))
        except (TypeError, ValueError):
            return float("nan")
        return value

    out: Dict[str, float] = {
        "lowest_fare": number("lowest_fare"),
        "highest_fare": number("highest_fare"),
        "average_fare": number("average_fare"),
        "median_fare": number("median_fare"),
        "fare_spread": number("fare_spread"),
        "price_std_dev": number("price_std_dev"),
        "total_live_flights": number("total_live_flights"),
    }
    out.update(stop_ratios(number("direct_flight_count"),
                           number("connecting_flight_count")))
    distribution = field("airline_distribution") or {}
    out["airline_diversity"] = (float(len(distribution)) if distribution
                               else float("nan"))
    out["snapshot_quality"] = number("snapshot_quality")
    out["snapshot_completeness"] = number("snapshot_completeness")
    return out
