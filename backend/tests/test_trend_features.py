"""Moving averages over one named flight's recent fares.

Same correction as `test_volatility_features`: the history rows and the request named
no airline and no departure, and a missing key component renders as the string
`"NONE"`, so three unidentified observations of the route formed one curve. Named, the
window and the numbers are unchanged.

The per-flight component is `departure_time`, not `flight_number`. These fixtures
named the flight number, which `BOOKING_CURVE_KEYS` stopped containing on 2026-09-03
— Google Flights publishes no flight number, so on real rows the column is NULL and
an identity built from it identifies nothing. `departure_time` is what the shipped key
asks for and what the provider actually returns; `flight_number` is not in these
fixtures at all, because a column the key ignores has no business standing in for the
flight's identity in a test about that identity.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np

from backend.ml.feature_context import FeatureContext
from backend.ml.features.trend import TrendGenerator

NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)

HISTORY: List[Dict[str, Any]] = [
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
     "departure_time": "06:10", "departure_date": "2026-07-26",
     "price": 5000.0, "recorded_at": "2026-07-19T12:00:00Z"},
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
     "departure_time": "06:10", "departure_date": "2026-07-26",
     "price": 5200.0, "recorded_at": "2026-07-20T12:00:00Z"},
]

QUERY: Dict[str, Any] = {
    "origin": "DEL", "destination": "BOM", "airline": "6E",
    "departure_time": "06:10", "departure_date": "2026-07-26",
    "current_price": 5500.0,
}


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


def test_trend_features_inference():
    """{5000, 5200, 5500}, adjust=False, spans counted in observations."""
    feats = TrendGenerator().transform(_context(QUERY))

    # alpha 2/8: 5000 → 5050 → 5162.5
    assert feats["ema_7"] == 5162.5
    assert feats["ema_14"] > 5000.0
    assert feats["ema_14"] < feats["ema_7"]
    assert feats["rolling_median_7"] == 5200.0
    assert feats["rolling_mean_14"] == 5233.333333333333
    # The short average is above the long one on a rising curve.
    assert feats["trend_direction"] == 1.0


def test_a_request_that_names_no_flight_has_no_trend():
    """Unnamed, the window was the quote alone.

    Every moving average then equalled that single fare, `trend_direction` was 0.0
    — "flat" — and `trend_duration` 1.0, for a flight whose price history had not
    been looked at.

    The component removed is `departure_time`. Removing `flight_number` instead, as
    this test used to, no longer changes the identity at all: it would assert NaN
    against a request the generator can still resolve, and would have passed on the
    day the key changed while `test_trend_features_inference` broke.
    """
    unnamed = TrendGenerator().transform(
        _context({**QUERY, "departure_time": None}))
    for name, value in unnamed.items():
        assert np.isnan(value), f"{name} was answered for an unnamed flight"
