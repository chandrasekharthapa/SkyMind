"""Airline aggregates at serve time: as-of, keyed on (route, airline), ddof=1.

This file used to assert `airline_average_fare == 5500.0` and
`airline_market_share == 2/3` from three history rows carrying **no timestamp**.
Under the as-of contract an observation with no observation time has no place on
the timeline and is not admitted to a window bounded by "at or before t", so the
old numbers came from a whole-history average that ignored ordering.

The fixture below timestamps its history and supplies the fare being quoted, which
is what `prediction_service` sends. Two airlines fly the route, so the rank and
the market share have a denominator above one and are not constants.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pytest

from backend.ml.feature_context import FeatureContext
from backend.ml.features.airline import AirlineGenerator

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)

# Two AI observations and one 9W, all on DEL-BOM, all ordered and priced.
HISTORY: List[Dict[str, Any]] = [
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI",
     "price": 5000.0, "departure_date": "2026-08-01",
     "search_timestamp": "2026-07-17T09:00:00+00:00"},
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI",
     "price": 6000.0, "departure_date": "2026-08-01",
     "search_timestamp": "2026-07-18T09:00:00+00:00"},
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "9W",
     "price": 4000.0, "departure_date": "2026-08-01",
     "search_timestamp": "2026-07-17T10:00:00+00:00"},
]


def _context(history: List[Dict[str, Any]], query: Dict[str, Any]) -> FeatureContext:
    return FeatureContext(
        historical_data=history,
        market_snapshot={},
        prediction_context=query,
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=NOW,
    )


def _quote(airline: str, price: float) -> Dict[str, Any]:
    return {"origin": "DEL", "destination": "BOM", "airline": airline,
            "current_price": price, "departure_date": "2026-08-01"}


def test_airline_features_inference():
    """AI's window is its own two fares plus the one being quoted."""
    feats = AirlineGenerator().transform(_context(HISTORY, _quote("AI", 7000.0)))

    assert feats["airline_code"] == "AI"
    assert feats["airline_average_fare"] == 6000.0          # mean of 5000, 6000, 7000
    assert feats["airline_observation_count"] == 3.0
    # 3 of the route's 4 observations are AI's — the quote counts on both sides.
    assert feats["airline_market_share"] == 0.75
    # AI's as-of mean 6000 against 9W's 4000: AI is the dearer of the two.
    assert feats["airline_price_rank"] == 2.0
    # One route in the corpus, so AI is on all of it.
    assert feats["airline_route_share"] == 1.0


def test_the_rank_is_a_rank_not_a_constant():
    """Quote the cheaper airline and the rank moves, on the same history."""
    cheap = AirlineGenerator().transform(_context(HISTORY, _quote("9W", 3500.0)))
    assert cheap["airline_price_rank"] == 1.0
    assert cheap["airline_average_fare"] == 3750.0           # mean of 4000, 3500
    assert cheap["airline_observation_count"] == 2.0
    assert cheap["airline_market_share"] == 0.5


def test_the_airline_dispersion_is_the_sample_std():
    """ddof=1, matching training; `np.std` gave ddof=0 under the same name."""
    feats = AirlineGenerator().transform(_context(HISTORY, _quote("AI", 7000.0)))
    prices = [5000.0, 6000.0, 7000.0]
    assert feats["airline_volatility"] == pytest.approx(float(np.std(prices, ddof=1)))
    assert feats["airline_volatility"] == 1000.0
    assert feats["airline_volatility"] != pytest.approx(float(np.std(prices, ddof=0)))


def test_one_observation_has_no_volatility_rather_than_zero():
    """A single fare shows no variation because there is nothing to vary against."""
    feats = AirlineGenerator().transform(
        _context([HISTORY[2]], _quote("AI", 7000.0)))
    assert feats["airline_observation_count"] == 1.0
    assert np.isnan(feats["airline_volatility"])


def test_untimestamped_history_is_not_admitted_to_the_window():
    """Only the quote survives, so every statistic is the quote's own."""
    undated = [{k: v for k, v in row.items() if k != "search_timestamp"}
               for row in HISTORY]
    feats = AirlineGenerator().transform(_context(undated, _quote("AI", 7000.0)))

    assert feats["airline_average_fare"] == 7000.0
    assert feats["airline_observation_count"] == 1.0
    assert feats["airline_market_share"] == 1.0
    assert np.isnan(feats["airline_volatility"])


def test_an_unknown_route_reports_unknown_not_a_default():
    """No route means no market to rank within, and nothing is invented."""
    feats = AirlineGenerator().transform(
        _context(HISTORY, {"airline": "AI", "current_price": 7000.0}))
    for name in ["airline_average_fare", "airline_market_share",
                 "airline_route_share", "airline_price_rank",
                 "airline_volatility", "airline_observation_count"]:
        assert np.isnan(feats[name]), f"{name} was invented for an unknown route"
