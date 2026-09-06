"""Curve features at serve time: one named flight's own price history.

This file used to pass three observations that named **no airline and no departure**
— on either the history rows or the request — and assert that they formed one booking
curve three points long. They did, because `get_booking_curve_group_key` renders a
missing component as the string `"NONE"`, so every unidentified observation on a route
and date collapsed into the same key. That is the defect the per-flight component of
`BOOKING_CURVE_KEYS` exists to stop, arriving through the key's own null handling.

That component is `departure_time`. It was `flight_number` when this file was written,
and the fixtures below named a flight number: `6E2341` for the curve and `6E9999` for
the sibling. Google Flights publishes no flight number on any of the 65 flights a live
DEL-BOM fetch returned, so an identity built on it is NULL on every honestly-collected
row, and the key changed to the departure time on 2026-09-03. The fixtures name a
departure time now; `6E9999` is `19:45`, an evening departure of the same carrier on
the same route and date.

The numbers are unchanged — the same three observations, a real curve — and
`days_until_dep` is left on the request set to a deliberately wrong 99 to show that the
horizon is derived from the departure date and the request time rather than read from
what the caller passed.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np

from backend.ml.feature_context import FeatureContext
from backend.ml.features.booking_curve import BookingCurveGenerator

NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)

HISTORY: List[Dict[str, Any]] = [
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
     "departure_time": "06:10", "departure_date": "2026-07-26",
     "price": 5000.0, "recorded_at": "2026-07-19T12:00:00Z"},
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
     "departure_time": "06:10", "departure_date": "2026-07-26",
     "price": 5200.0, "recorded_at": "2026-07-20T12:00:00Z"},
]


def _context(query: Dict[str, Any]) -> FeatureContext:
    return FeatureContext(
        historical_data=HISTORY,
        market_snapshot={},
        prediction_context=query,
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=NOW,
    )


def _query(**overrides: Any) -> Dict[str, Any]:
    query = {
        "origin": "DEL", "destination": "BOM", "airline": "6E",
        "departure_time": "06:10", "departure_date": "2026-07-26",
        "current_price": 5500.0,
        # Not read. The horizon comes from the departure date and the request
        # time, which here is 5 days, and every feature below is consistent with
        # that rather than with this number.
        "days_until_dep": 99,
    }
    query.update(overrides)
    return query


def test_booking_curve_features_inference():
    """Two retrieved observations plus the fare being quoted, in order."""
    feats = BookingCurveGenerator().transform(_context(_query()))

    assert feats["days_since_first_observation"] == 2.0
    assert feats["observation_count"] == 3
    assert feats["price_change_1d"] == 300.0            # 5500 - 5200
    assert feats["rolling_mean_price"] == 5233.333333333333
    # 2 days along a curve whose flight leaves in 5: 2 / (2 + 5), and not 2 / 101.
    assert feats["booking_curve_progress"] == 2.0 / 7.0


def test_a_request_that_names_no_flight_has_no_curve():
    """The same history, with and without the departure named on the request.

    Without it the key's per-flight component was the string `"NONE"`, which matched
    nothing that carried a real departure time, so the window was the quoted fare
    by itself and every feature was a statistic of it: `observation_count` 1.0,
    `days_since_first_observation` 0.0, `booking_curve_progress` 0.0 and all four
    `rolling_*` equal to 5500.0. The model was fitted on these names computed over
    real curves.
    """
    unnamed = BookingCurveGenerator().transform(
        _context(_query(departure_time=None)))

    for name in ["days_since_first_observation", "observation_count",
                 "booking_curve_progress", "rolling_mean_price",
                 "rolling_median_price", "rolling_min_price", "rolling_max_price",
                 "rolling_price_std", "price_change_1d", "price_change_3d",
                 "price_change_7d", "price_slope", "price_acceleration"]:
        assert np.isnan(unnamed[name]), f"{name} was answered for an unnamed flight"

    # `seats_available` is not a curve statistic — it is what the request said —
    # so it survives, and is null here because the request did not say.
    assert np.isnan(unnamed["seats_available"])
    assert BookingCurveGenerator().transform(
        _context(_query(departure_time=None, seats_available=12))
    )["seats_available"] == 12.0


def test_history_from_another_flight_is_not_this_flight_s_curve():
    """A different departure time on the same route, date and airline.

    The distinction from the test above: this identity is *complete*, so the curve
    exists and simply has no history behind it, and the features are the quote's own
    statistics rather than unknown.
    """
    feats = BookingCurveGenerator().transform(
        _context(_query(departure_time="19:45")))

    # Only the quote is on this curve, so it is one observation old and there is
    # nothing earlier to change against.
    assert feats["observation_count"] == 1.0
    assert feats["days_since_first_observation"] == 0.0
    assert np.isnan(feats["price_change_1d"])
    assert feats["rolling_mean_price"] == 5500.0
