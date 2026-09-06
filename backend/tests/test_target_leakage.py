"""The label must never be the fare the features describe.

This test is named after the defect that made the reported r² of 0.932
meaningless, and it used to be unable to detect it: it called
`PricePredictor._build_shifted_dataset`, which production never invoked, and its
fixture held one flight so a label that crossed flights looked identical to one
that did not.

`_build_shifted_dataset` now delegates to
`booking_curve_definition.attach_future_target` — the same function
`training_dataset_builder.build` calls — so this test finally inspects the join
the model is trained on.
"""

import pytest
import sys
import os
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.ml.price_model import PricePredictor
from backend.services.booking_curve_definition import MIN_TRAINABLE_HORIZON_DAYS

BASE = "2026-07-"
# Two departures, same route, same airline, same departure date: `departure_time` is
# the only key separating them, which is exactly the key the old join dropped.
#
# The discriminator was `flight_number` (`AI101` and `AI202`) until 2026-09-03. It is
# `departure_time` because that is what `BOOKING_CURVE_KEYS` names and what the
# provider actually publishes — on a flight number, which is NULL on every real row,
# these two curves would pool and this test would assert nothing.
CURVES = {"06:10": [5000.0, 5200.0, 5800.0], "19:45": [9000.0, 8600.0, 8000.0]}
DAYS = ["19", "20", "22"]


def _frame():
    return pd.DataFrame([
        {
            "origin_code": "DEL",
            "destination_code": "BOM",
            "airline_code": "AI",
            "departure_time": departure,
            "departure_date": "2026-08-26",
            "recorded_at": f"2026-07-{day}T12:00:00+00:00",
            "price": price,
        }
        for departure, prices in CURVES.items()
        for day, price in zip(DAYS, prices)
    ])


def test_no_target_leakage():
    """No labelled row's target is its own observed fare, at any trainable horizon."""
    predictor = PricePredictor()
    for horizon in predictor.supported_horizons:
        shifted = predictor._build_shifted_dataset(_frame(), horizon=horizon)
        for _, row in shifted.iterrows():
            assert row["target_price"] != row["price"], (
                f"horizon {horizon}: target equals the feature row's own fare"
            )


def test_target_is_the_observation_h_days_later():
    """At horizon 3 the only labellable row on each curve takes the 07-22 fare."""
    shifted = PricePredictor()._build_shifted_dataset(_frame(), horizon=3)
    got = dict(zip(shifted["departure_time"], shifted["target_price"]))
    # The morning departure rises to 5800 and the evening one falls to 8000. A join
    # that pooled the two would hand at least one of them the other's fare.
    assert got == {"06:10": 5800.0, "19:45": 8000.0}


def test_horizon_zero_is_refused_rather_than_scored():
    """The identity label is an error, not a result.

    At horizon 0 `target_price` is the price on the same row as the features, so
    the fit is an identity and its r² restates the join. There is no masking or
    shifting that detects it — the leaking row *is* the labelled row — so the
    only correct behaviour is to refuse.
    """
    with pytest.raises(ValueError, match="not a trainable target"):
        PricePredictor()._build_shifted_dataset(_frame(), horizon=0)
    assert MIN_TRAINABLE_HORIZON_DAYS >= 1
