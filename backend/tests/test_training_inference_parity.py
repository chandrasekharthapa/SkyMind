"""Train and serve must produce the same number for the same observation.

This test used to pass on a **one-row** frame. Every group aggregate over a
one-row group degenerates to that row's own price, so both paths agreed on
numbers that were wrong in the same way, and eight features were exempted for
"structural divergence between training and inference" —

    observation_count, booking_curve_progress, price_change_1d,
    price_change_3d, price_change_7d, is_live, volatility_trend, trend_duration

Not one of those was structural. They were artefacts of the fixture: with a
single observation there is nothing to lag against, no second point to measure a
trend over, and `is_live` was a literal `False` in training against a literal
`True` at inference. On the corpus below — two routes, five booking curves, three
airlines, twelve search days, 60 observations — **every feature of both feature
sets agrees on every row, and the exemption list is empty.**

The corpus is shaped like the real ingestion: one `search_timestamp` per day
shared by every flight, so a `(route, search_timestamp)` group is one search;
`recorded_at` is a single nightly batch write hours later, so anything keyed on
`recorded_at` instead would pool searches taken hours apart and read fares quoted
after the row.

Serve-side history is the observations at or before the row's own timestamp,
minus the row itself, which is re-supplied as the fare being quoted. That is what
the retrieval query returns in production. Handing over the whole frame is not a
stricter test but a broken one: the as-of route and airline aggregates mask by
timestamp and would be unaffected, while the curve-window features sort and read
the last point, so they would silently see forward.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import pytest

from backend.ml.feature_context import FeatureContext
from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline
from backend.ml.feature_metadata import FEATURE_SET_V1, LEGACY_FEATURE_SET
from backend.services.booking_curve_definition import BOOKING_CURVE_KEYS
from backend.services.market_aggregate_definition import (
    STD_DDOF,
    snapshot_completeness_score,
    snapshot_quality_score,
)

DEPARTURE_DATE = "2026-07-26"
# Five departures inside the same peak hour. 08:30 and its neighbours are inside
# PEAK_HOURS, so `is_peak_hour` is 1.0 rather than the 0.0 a NaN hour used to produce
# through `.isin`, and the minutes differ so the five are five booking curves.
#
# One shared `DEPARTURE_TIME` used to sit here, with `flight_number` separating the
# curves. `BOOKING_CURVE_KEYS` names `departure_time` as the per-flight component
# since 2026-09-03, so a shared departure time now pools all five: the two DEL-BOM AI
# flights would become one curve, the parity assertion would compare a pooled history
# against itself, and the group floor below would fall.
DEPARTURE_TIMES = ["08:30:00", "08:35:00", "08:40:00", "08:45:00", "08:50:00"]
SEARCH_DAYS = 12
FIRST_SEARCH_DAY = date(2026, 7, 8)

# (origin, destination, airline, flight number, stops, base fare, amplitude).
# Two routes so `airline_route_share` has a denominator above 1; three airlines
# so `airline_diversity` and `airline_price_rank` are not constants; one airline
# on both routes and two on one each, so the shares differ per airline.
#
# `flight_number` stays in the frame and stays populated. It is a real column of
# `price_history`, it is not part of the curve key, and nothing below may read it —
# leaving it here and distinct per flight means a feature that regressed to it would
# still produce five curves and the regression would hide. The group floor therefore
# asserts over `BOOKING_CURVE_KEYS` itself rather than a typed-out list.
FLIGHTS: List[Tuple[str, str, str, str, int, float, float]] = [
    ("DEL", "BOM", "AI", "AI-101", 0, 4200.0, 61.0),
    ("DEL", "BOM", "AI", "AI-202", 0, 4800.0, 53.0),
    ("DEL", "BOM", "6E", "6E-303", 1, 3600.0, 87.0),
    ("BOM", "BLR", "AI", "AI-505", 0, 3100.0, 44.0),
    ("BOM", "BLR", "UK", "UK-808", 1, 2700.0, 71.0),
]

def _corpus() -> pd.DataFrame:
    """Sixty observations of five booking curves over twelve searches."""
    rows: List[Dict[str, Any]] = []
    for day_offset in range(SEARCH_DAYS):
        day = date(FIRST_SEARCH_DAY.year, FIRST_SEARCH_DAY.month,
                   FIRST_SEARCH_DAY.day + day_offset)
        until = float((date(2026, 7, 26) - day).days)
        searched = datetime(day.year, day.month, day.day, 9, 0, tzinfo=timezone.utc)
        batched = datetime(day.year, day.month, day.day, 23, 45, tzinfo=timezone.utc)
        for index, (origin, destination, airline, number, stops, base, amp) in \
                enumerate(FLIGHTS):
            # Deterministic, non-monotone and per-flight, so no two windows can
            # agree by accident and a rewrite that pools two curves shows up.
            price = round(base + amp * ((day_offset * 7 + len(number)) % 11)
                          - 3.5 * day_offset, 2)
            rows.append({
                "origin_code": origin,
                "destination_code": destination,
                "airline_code": airline,
                "flight_number": number,
                "departure_date": DEPARTURE_DATE,
                "departure_time": f"{DEPARTURE_DATE}T{DEPARTURE_TIMES[index]}",
                "search_timestamp": searched.isoformat(),
                "recorded_at": batched.isoformat(),
                "price": price,
                "stops": stops,
                "seats_available": 9 + (day_offset % 5),
                "days_until_dep": until,
                "is_live": True,
            })
    return pd.DataFrame(rows, index=pd.RangeIndex(len(rows)))


@pytest.fixture(scope="module")
def corpus() -> Tuple[pd.DataFrame, pd.Series]:
    frame = _corpus()
    times = pd.to_datetime(frame["search_timestamp"], utc=True, format="mixed")
    return frame, times


def _serve(frame: pd.DataFrame, times: pd.Series, label: Any, version: str):
    """The serve-side feature vector for one row of `frame`."""
    row = frame.loc[label]
    moment = times.loc[label]
    history = frame[(times <= moment) & (frame.index != label)].to_dict("records")

    # The row's own search is the live snapshot: same route, same instant. The
    # statistics are the ones `MarketSnapshotProvider` computes, through the same
    # shared functions, so this is the payload production hands the generator.
    group = frame[(frame["origin_code"] == row["origin_code"])
                  & (frame["destination_code"] == row["destination_code"])
                  & (frame["search_timestamp"] == row["search_timestamp"])]
    fares = pd.to_numeric(group["price"])
    total = float(len(group))
    priced = float(fares.notna().sum())
    snapshot = {
        "lowest_fare": float(fares.min()),
        "highest_fare": float(fares.max()),
        "average_fare": float(fares.mean()),
        "median_fare": float(fares.median()),
        "fare_spread": float(fares.max() - fares.min()),
        "price_std_dev": float(fares.std(ddof=STD_DDOF)),
        "total_live_flights": total,
        "direct_flight_count": float((group["stops"] == 0).sum()),
        "connecting_flight_count": float((group["stops"] > 0).sum()),
        "airline_distribution": group["airline_code"].value_counts().to_dict(),
        "snapshot_quality": snapshot_quality_score(total, priced),
        "snapshot_completeness": snapshot_completeness_score(total, priced),
    }

    context = FeatureContext(
        historical_data=history,
        market_snapshot=snapshot,
        prediction_context={
            "origin": row["origin_code"],
            "destination": row["destination_code"],
            "airline": row["airline_code"],
            "flight_number": row["flight_number"],
            "departure_date": DEPARTURE_DATE,
            "departure_time": row["departure_time"],
            "current_price": float(row["price"]),
            "seats_available": float(row["seats_available"]),
            "days_until_dep": float(row["days_until_dep"]),
        },
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=pd.Timestamp(row["search_timestamp"]).to_pydatetime(),
    )
    return feature_engineering_pipeline.build(context, version)


def _agree(left: Any, right: Any) -> bool:
    """Equal, or unknown on both sides. NaN and None are the same answer here."""
    left_unknown = left is None or (isinstance(left, float) and np.isnan(left))
    right_unknown = right is None or (isinstance(right, float) and np.isnan(right))
    if left_unknown or right_unknown:
        return left_unknown and right_unknown
    try:
        return abs(float(left) - float(right)) <= 1e-9
    except (TypeError, ValueError):
        return str(left) == str(right)


@pytest.mark.parametrize("version, definitions", [
    ("feature_set_v1", FEATURE_SET_V1),
    # The legacy set is what the shipped model artifacts declare, so parity has
    # to hold there too and not only on the set the rewrite was aimed at.
    ("legacy", LEGACY_FEATURE_SET),
])
def test_every_feature_agrees_on_every_row(corpus, version, definitions):
    """No exemption list. Every feature, every row, both feature sets."""
    frame, times = corpus
    trained = feature_engineering_pipeline.build_training_dataset(frame, version)
    names = [definition.name for definition in definitions]

    divergences: List[str] = []
    compared = 0
    for label in frame.index:
        served = _serve(frame, times, label, version)
        for name in names:
            compared += 1
            train_value = trained.at[label, name]
            serve_value = served.features[name]
            if not _agree(train_value, serve_value):
                divergences.append(
                    f"row {label} {name}: train={train_value!r} serve={serve_value!r}")

    assert compared == len(frame) * len(names)
    assert not divergences, (
        f"{len(divergences)} of {compared} train/serve comparisons disagree on "
        f"'{version}':\n" + "\n".join(divergences[:25]))


def test_the_fixture_is_not_degenerate(corpus):
    """The guard on the defect this file used to have.

    A one-row frame makes every aggregate equal the row's own price, so the two
    paths can agree while both are wrong. If a future edit shrinks the corpus or
    collapses it onto one route, one airline or one curve, the parity assertion
    above stops meaning anything — and it would still pass. These floors are what
    make it a measurement.
    """
    frame, _ = corpus
    trained = feature_engineering_pipeline.build_training_dataset(
        frame, "feature_set_v1")

    assert len(frame) >= 40
    assert frame.groupby(["origin_code", "destination_code"]).ngroups >= 2
    assert frame["airline_code"].nunique() >= 3
    assert frame.groupby(list(BOOKING_CURVE_KEYS)).ngroups >= 4

    for column, floor in [("historical_average_fare", 3), ("airline_price_rank", 2),
                          ("airline_route_share", 2), ("observation_density", 5),
                          ("rolling_price_std", 5), ("ema_7", 10)]:
        distinct = trained[column].nunique(dropna=True)
        assert distinct >= floor, (
            f"{column} takes only {distinct} distinct values across the corpus; "
            "the fixture is too degenerate for parity on it to mean anything")


def test_a_curves_first_observation_is_unknown_on_both_paths(corpus):
    """Nothing to compare against is NaN on both sides, not 0.0 on either."""
    frame, times = corpus
    trained = feature_engineering_pipeline.build_training_dataset(
        frame, "feature_set_v1")
    first = frame.index[0]
    served = _serve(frame, times, first, "feature_set_v1")

    for name in ["price_change_1d", "price_change_3d", "price_change_7d",
                 "price_slope", "price_acceleration", "rolling_price_std",
                 "rolling_volatility", "coefficient_of_variation",
                 "trend_strength", "volatility_trend"]:
        assert pd.isna(trained.at[first, name]), f"training filled {name}"
        assert pd.isna(served.features[name]), f"inference filled {name}"


def test_route_dispersion_is_defined_where_the_curve_window_is_not(corpus):
    """The route window and the curve window are different windows, on purpose.

    A curve's first observation has nothing behind it, but the route it flies had
    three flights quoted at that same instant — so the route's dispersion is
    already measurable there while the flight's is not. Both paths agree on that
    too, which is what keying them separately is for.
    """
    frame, times = corpus
    trained = feature_engineering_pipeline.build_training_dataset(
        frame, "feature_set_v1")
    first = frame.index[0]
    served = _serve(frame, times, first, "feature_set_v1")

    for name in ["historical_price_std", "airline_volatility"]:
        train_value = trained.at[first, name]
        assert pd.notna(train_value), f"{name} should be known on a 3-flight search"
        assert _agree(train_value, served.features[name])


def test_departure_hour_is_unknown_on_both_paths_without_the_column(corpus):
    """`price_history` carries no `departure_time`, and that reads as unknown.

    `hours.isin(PEAK_HOURS)` is False for NaN, so an unreadable departure time
    used to report "not a peak-hour flight" rather than "unknown". Both features
    are legacy-set only.
    """
    frame, times = corpus
    with_time = feature_engineering_pipeline.build_training_dataset(frame, "legacy")
    served = _serve(frame, times, frame.index[-3], "legacy")
    assert with_time.at[frame.index[-3], "hour_of_day"] == 8.0
    assert served.features["hour_of_day"] == 8.0
    assert with_time.at[frame.index[-3], "is_peak_hour"] == 1.0
    assert served.features["is_peak_hour"] == 1.0

    without_time = feature_engineering_pipeline.build_training_dataset(
        frame.drop(columns=["departure_time"]), "legacy")
    assert without_time["hour_of_day"].isna().all()
    assert without_time["is_peak_hour"].isna().all()
    assert not (without_time["is_peak_hour"] == 0.0).any()


def test_snapshot_features_are_computed_not_literals(corpus):
    """`snapshot_quality` was the literal 1.0 for every training row.

    The model was trained to treat it as a constant and then shown 0.72 in
    production. Here the two-flight route earns the sparsity discount and the
    three-flight route does not, so the column actually varies.
    """
    frame, _ = corpus
    trained = feature_engineering_pipeline.build_training_dataset(
        frame, "feature_set_v1")

    assert trained["total_live_flights"].max() == 3.0
    assert (trained["snapshot_completeness"] == 1.0).all()
    assert (trained.loc[trained["total_live_flights"] == 2.0,
                        "snapshot_quality"] == 0.9).all()
    assert (trained.loc[trained["total_live_flights"] == 3.0,
                        "snapshot_quality"] == 1.0).all()
    assert trained["snapshot_quality"].nunique() == 2
