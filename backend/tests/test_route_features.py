"""Route aggregates at serve time: as-of, ddof=1, and nothing filled.

This file used to assert `historical_average_fare == 5500.0` from two history rows
that carried **no timestamp at all**. Under the as-of contract an observation with
no observation time has no place on the timeline, so it cannot be admitted to a
window bounded by "at or before t" — and the old fixture's rows are exactly that.
The mean it asserted came from a whole-history average that ignored ordering,
which is the defect `market_aggregate_definition` was written to remove.

The fixture below timestamps its history and supplies the fare being quoted, which
is what `prediction_service` actually sends. The window is then three
observations — two retrieved, one quoted — and every expected number is arithmetic
over those three.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pytest

from backend.ml.feature_context import FeatureContext
from backend.ml.features.route import RouteGenerator

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)

# Two prior observations of the same route, ordered and priced. `days_until_dep`
# is deliberately wrong on both: the horizon is derived from `departure_date` and
# the observation time, and this column — an ingest-time denormalisation of
# exactly that subtraction — is no longer read by any feature.
HISTORY: List[Dict[str, Any]] = [
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI",
     "price": 5000.0, "days_until_dep": 99, "departure_date": "2026-08-01",
     "search_timestamp": "2026-07-17T09:00:00+00:00"},
    {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI",
     "price": 6000.0, "days_until_dep": 99, "departure_date": "2026-08-01",
     "search_timestamp": "2026-07-18T09:00:00+00:00"},
]

QUERY: Dict[str, Any] = {
    "origin": "DEL", "destination": "BOM", "airline": "AI",
    "current_price": 7000.0, "days_until_dep": 99,
    "departure_date": "2026-08-01",
}


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


def test_route_features_inference():
    """The window is the two retrieved fares plus the one being quoted."""
    feats = RouteGenerator().transform(_context(HISTORY, QUERY))

    assert feats["origin_code"] == "DEL"
    assert feats["destination_code"] == "BOM"
    # mean/median/min/max over {5000, 6000, 7000}. The quote is an observation and
    # it is known now, so it belongs in the window its own features describe.
    assert feats["historical_average_fare"] == 6000.0
    assert feats["historical_median_fare"] == 6000.0
    assert feats["historical_minimum_fare"] == 5000.0
    assert feats["historical_maximum_fare"] == 7000.0
    assert feats["airline_count"] == 1.0
    assert feats["observation_density"] == 3.0
    # The horizon of each observation is its own departure date minus its own
    # observation date — 15, 14 and the quote's 13 — so the mean is 14.0, not the
    # 14.5 the history alone would give and not the 99.0 the `days_until_dep`
    # column on every one of these rows claims.
    assert feats["average_booking_lead"] == 14.0


def test_the_route_dispersion_is_the_sample_std():
    """ddof=1, which is what the training path computes.

    Inference used `np.std` (ddof=0) under the same feature name. On this window
    that is 816.50 against 1000.0 — a 22% difference in a feature the model was
    fitted on.
    """
    feats = RouteGenerator().transform(_context(HISTORY, QUERY))
    prices = [5000.0, 6000.0, 7000.0]
    assert feats["historical_price_std"] == pytest.approx(float(np.std(prices, ddof=1)))
    assert feats["historical_price_std"] == 1000.0
    assert feats["historical_price_std"] != pytest.approx(float(np.std(prices, ddof=0)))


def test_untimestamped_history_is_not_admitted_to_the_window():
    """A record with no observation time cannot be placed relative to the quote.

    Dropping it is the whole content of the as-of rule: a statistic that admits
    rows it cannot order is a statistic over the whole corpus, which is how a
    row's own future got into its own features.
    """
    undated = [{k: v for k, v in row.items() if k != "search_timestamp"}
               for row in HISTORY]
    feats = RouteGenerator().transform(_context(undated, QUERY))

    # Only the quote survives, so the mean is the quote and there is no dispersion.
    assert feats["historical_average_fare"] == 7000.0
    assert feats["observation_density"] == 1.0
    assert np.isnan(feats["historical_price_std"])


def test_a_single_observation_has_no_dispersion_rather_than_zero():
    """`historical_price_std` was `.fillna(0.0)`: "this route showed no variation"."""
    feats = RouteGenerator().transform(_context([], QUERY))
    assert feats["historical_average_fare"] == 7000.0
    assert feats["observation_density"] == 1.0
    assert np.isnan(feats["historical_price_std"])


def test_the_booking_lead_is_derived_not_read_from_the_column():
    """Take the departure dates away and the horizon is unknown, not 99.

    `average_booking_lead` used to be the as-of mean of the `days_until_dep`
    column. That column is written at ingest as `departure_date - recorded_at`,
    and three other features — `days_until_departure`, `urgency` and
    `booking_curve_progress` — derive the same quantity from the same pair, so a
    single feature vector could carry two horizons that disagreed. Every row in
    this fixture claims 99 days; with the departure dates present the mean is
    14.0, and with them removed the feature is null rather than 99.0.
    """
    with_dates = RouteGenerator().transform(_context(HISTORY, QUERY))
    assert with_dates["average_booking_lead"] == 14.0

    stripped = [{k: v for k, v in row.items() if k != "departure_date"}
                for row in HISTORY]
    query = {k: v for k, v in QUERY.items() if k != "departure_date"}
    feats = RouteGenerator().transform(_context(stripped, query))

    assert np.isnan(feats["average_booking_lead"])
    # The rest of the window is unaffected: only the horizon needed those dates.
    assert feats["historical_average_fare"] == 6000.0
    assert feats["observation_density"] == 3.0


def test_an_unknown_route_reports_unknown_not_a_default():
    """With no route there is no market to describe, and nothing is invented."""
    feats = RouteGenerator().transform(_context(HISTORY, {"current_price": 7000.0}))
    for name in ["historical_average_fare", "historical_median_fare",
                 "historical_minimum_fare", "historical_maximum_fare",
                 "historical_price_std", "airline_count", "average_booking_lead",
                 "observation_density"]:
        assert np.isnan(feats[name]), f"{name} was invented for an unknown route"
