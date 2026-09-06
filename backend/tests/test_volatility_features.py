"""Dispersion over one named flight's recent fares.

This file used to pass history rows and a request that named **no airline and no
departure**, and got a three-observation window anyway: a missing key component
renders as the string `"NONE"`, so every unidentified observation on the route and
date collapsed into one curve. With the flight named the window is the same three
fares and the numbers are the same; with it left off, the window is the quoted fare
alone and every feature here is unknown rather than a statistic of one number.

The per-flight component is `departure_time`. These fixtures named `flight_number`,
which `BOOKING_CURVE_KEYS` stopped containing on 2026-09-03 because the provider
publishes no flight number — see the header of `test_trend_features` for the same
correction.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np

from backend.ml.feature_context import FeatureContext
from backend.ml.features.volatility import VolatilityGenerator

NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)

HISTORY: List[Dict[str, Any]] = [
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
     "departure_time": "06:10", "departure_date": "2026-07-26",
     "price": 5000.0, "recorded_at": "2026-07-19T12:00:00Z"},
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
     "departure_time": "06:10", "departure_date": "2026-07-26",
     "price": 6000.0, "recorded_at": "2026-07-20T12:00:00Z"},
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


def test_volatility_features_inference():
    """{5000, 6000, 5500}: sample std 500.0, range 1000.0."""
    feats = VolatilityGenerator().transform(_context(QUERY))

    assert feats["rolling_volatility"] == 500.0
    assert feats["rolling_price_range"] == 1000.0
    assert feats["coefficient_of_variation"] == 500.0 / 5500.0
    assert feats["rolling_iqr"] == 500.0


def test_a_request_that_names_no_flight_has_no_volatility():
    """Unnamed, the window was the quote alone: range 0.0 and iqr 0.0.

    Those are claims about a flight's price behaviour drawn from one observation
    of it. The window is undefined, so the features are.
    """
    unnamed = VolatilityGenerator().transform(
        _context({**QUERY, "departure_time": None}))
    for name, value in unnamed.items():
        assert np.isnan(value), f"{name} was answered for an unnamed flight"
