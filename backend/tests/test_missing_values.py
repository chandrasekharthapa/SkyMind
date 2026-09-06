"""Nothing is invented when nothing is known.

This file used to end with a sweep that accepted `0.0`, `1.0`, `-1.0` or `1` for
every feature outside a sixteen-name allow-list:

    assert val is None or (isinstance(val, float) and np.isnan(val)) \\
        or val == 0.0 or val == 1.0 or val == -1.0 or val == 1

That is precisely the set of values the rewrite removed. `historical_price_std`
was `.fillna(0.0)`; `airline_market_share`, `airline_route_share` and
`airline_price_rank` answered 1.0 when the columns were absent; the calendar
fields used -1 sentinels. Every one of those could come back and this test would
stay green — it could not fail for the reason it was written for.

The expectations below are the measured split instead: which features are
knowable from a request that names a route and a departure date but carries no
price, no airline and no history, and what each of them is. Everything else is
unknown, by name. A returning fill moves a name from the unknown list to the
known one and the test fails on the set comparison.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from backend.ml.feature_context import FeatureContext
from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline
from backend.ml.feature_metadata import FEATURE_SET_V1

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
DEPARTURE = "2026-07-26"

# One prior observation, timestamped and priced, used to show that the zeros
# above are counts over an empty window rather than fills for an unknown one.
HISTORY: List[Dict[str, Any]] = [{
    "origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI",
    "price": 5000.0, "days_until_dep": 8, "flight_number": "AI101",
    "search_timestamp": "2026-07-18T09:00:00+00:00",
}]

# Everything a request for DEL-BOM on 2026-07-26 determines on its own.
KNOWN: Dict[str, Any] = {
    # The route is what was asked for.
    "origin_code": "DEL",
    "destination_code": "BOM",
    # Arithmetic on the departure date and the request time. `days_until_dep`,
    # `day_of_week`, `month` and `week_of_year` are legacy-set names and are not
    # in FEATURE_SET_V1, so they are absent here rather than unknown.
    "days_until_departure": 7.0,
    "departure_day_of_week": 6,
    "departure_month": 7,
    "departure_quarter": 3,
    "departure_week": 30,
    "is_weekend": True,
    "is_holiday": False,
    "is_long_weekend": False,
    # A live request is live. This is the one flag whose value is about the
    # caller rather than the market.
    "is_live": True,
    # Counts over windows that are well defined and empty. No airline and no
    # priced observation has been seen at or before now, so the count is zero —
    # a measurement, not a stand-in for one. `test_the_zero_counts_are_counts`
    # moves each of these by adding a single observation.
    #
    # `observation_count` is not here: it counts along a *booking curve*, and the
    # request names no flight, so there is no curve to be the nth observation of.
    # That is a different thing from an empty window and it is NaN, not 0.0.
    "airline_count": 0.0,
    "observation_density": 0.0,
    # The as-of mean booking horizon over the route's observations, which here is
    # the request and nothing else — so it is the request's own horizon, the same
    # 7.0 as `days_until_departure`. It is knowable for the same reason that one
    # is: `average_booking_lead` derives the horizon from the departure date and
    # the observation time rather than reading a stored `days_until_dep`.
    "average_booking_lead": 7.0,
}

# The six airline features, which describe the carrier the request names.
AIRLINE_FEATURE_NAMES = [
    "airline_average_fare", "airline_market_share", "airline_route_share",
    "airline_price_rank", "airline_volatility", "airline_observation_count",
]


def _context(airline: Optional[str], history: List[Dict[str, Any]]) -> FeatureContext:
    return FeatureContext(
        historical_data=history,
        market_snapshot=None,
        prediction_context={
            "origin": "DEL", "destination": "BOM", "airline": airline,
            "departure_date": DEPARTURE,
            "current_price": None, "seats_available": None,
        },
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=NOW,
    )


def _unknown(value: Any) -> bool:
    return value is None or (isinstance(value, float) and np.isnan(value))


def test_missing_values_no_synthetic_policy():
    """The known set is exactly KNOWN; every other v1 feature is unknown."""
    features = feature_engineering_pipeline.build(
        _context(None, []), "feature_set_v1").features

    # A feature added to the set without a decision about this case would sit in
    # neither list, so grade the whole set rather than the values it happens to
    # have produced.
    assert set(features) == {d.name for d in FEATURE_SET_V1}

    known = {name: value for name, value in features.items() if not _unknown(value)}
    assert set(known) == set(KNOWN), (
        "the set of features this request determines has changed:\n"
        f"  newly known: {sorted(set(known) - set(KNOWN))}\n"
        f"  no longer known: {sorted(set(KNOWN) - set(known))}")
    for name, expected in KNOWN.items():
        assert known[name] == expected, f"{name}: {known[name]!r} != {expected!r}"

    # The four the file was originally written to pin, still pinned by name.
    for name in ["seats_available", "rolling_mean_price",
                 "historical_average_fare", "airline_average_fare"]:
        assert np.isnan(features[name]), f"{name} was filled"


def test_the_zero_counts_are_counts_not_fills():
    """Add one observation and every zero that should move, moves."""
    empty = feature_engineering_pipeline.build(
        _context("AI", []), "feature_set_v1").features
    one = feature_engineering_pipeline.build(
        _context("AI", HISTORY), "feature_set_v1").features

    assert empty["observation_density"] == 0.0
    assert one["observation_density"] == 1.0
    assert empty["airline_observation_count"] == 0.0
    assert one["airline_observation_count"] == 1.0
    # And a statistic over that window becomes a number rather than staying NaN,
    # which is what distinguishes "no observations" from "no window".
    assert np.isnan(empty["historical_average_fare"])
    assert one["historical_average_fare"] == 5000.0

    # `observation_count` is the *curve* window — route, airline, departure and
    # flight number — and the request names no flight, so there is no curve for it
    # to count along and the feature is unknown on both variants. Two different
    # windows under two names, which is why both are asserted.
    assert np.isnan(empty["observation_count"])
    assert np.isnan(one["observation_count"])


def test_a_request_that_names_no_airline_has_no_airline_features():
    """The same history, with and without a carrier on the request.

    `_as_of` groups with `dropna=False`, so before the mask in
    `airline_aggregates` a null airline formed its own group and was answered:
    `airline_route_share` came back 1.0 — "this airline flies every route in the
    market" — for a request that named no airline at all, next to an
    `airline_code` of NaN.
    """
    named = feature_engineering_pipeline.build(
        _context("AI", HISTORY), "feature_set_v1").features
    unnamed = feature_engineering_pipeline.build(
        _context(None, HISTORY), "feature_set_v1").features

    assert named["airline_code"] == "AI"
    assert named["airline_route_share"] == 1.0
    assert named["airline_observation_count"] == 1.0
    assert named["airline_average_fare"] == 5000.0
    assert named["airline_market_share"] == 1.0
    assert named["airline_price_rank"] == 1.0

    assert np.isnan(unnamed["airline_code"])
    for name in AIRLINE_FEATURE_NAMES:
        assert np.isnan(unnamed[name]), f"{name} was answered for an unnamed airline"

    # The route features are not the airline's, so they are unaffected: the
    # market around the request is still the market around the request.
    assert unnamed["historical_average_fare"] == 5000.0
    assert unnamed["airline_count"] == 1.0
