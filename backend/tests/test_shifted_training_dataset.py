"""A row with no future observation is dropped, never zero-filled or self-labelled.

The dataset the model trains on is smaller than the dataset ingested, and it has
to be: the most recent observation on every booking curve has nothing after it to
predict. This test asserts that the shortfall is visible as *missing rows* rather
than as a label of 0.0, of the row's own price, or of another curve's fare.
"""

import pytest
import pandas as pd
from backend.ml.price_model import PricePredictor

CURVE = {
    "origin_code": "DEL",
    "destination_code": "BOM",
    "airline_code": "6E",
    "departure_time": "06:10",
    "departure_date": "2026-08-26",
}


def _frame(observations):
    return pd.DataFrame([
        {**CURVE, "recorded_at": ts, "price": price} for ts, price in observations
    ])


def test_shifted_training_dataset_joins():
    """Verify target shifts to future prices T + horizon, preventing current fare echo."""
    df = _frame([
        ("2026-07-19T12:00:00+00:00", 5000.0),
        ("2026-07-22T12:00:00+00:00", 5500.0),
    ])

    shifted = PricePredictor()._build_shifted_dataset(df, horizon=3)

    assert len(shifted) == 1
    row = shifted.iloc[0]
    assert row["price"] == 5000.0
    assert row["target_price"] == 5500.0


def test_rows_without_a_future_are_dropped_not_filled():
    """The tail of every curve is excluded, and no label is 0.0."""
    df = _frame([
        ("2026-07-19T12:00:00+00:00", 5000.0),
        ("2026-07-22T12:00:00+00:00", 5500.0),
        ("2026-07-25T12:00:00+00:00", 6100.0),
        ("2026-07-28T12:00:00+00:00", 6400.0),
    ])

    shifted = PricePredictor()._build_shifted_dataset(df, horizon=3)

    # Four observations, three of which have a fare three days later.
    assert len(shifted) == 3
    assert shifted["target_price"].notna().all()
    assert (shifted["target_price"] != 0.0).all()
    # The final observation is absent, not present with a filled label.
    assert 6400.0 not in set(shifted["price"])
    assert set(shifted["target_price"]) == {5500.0, 6100.0, 6400.0}


def test_a_single_observation_yields_no_training_rows():
    """One fare is a price, not a curve; it cannot be labelled at all."""
    df = _frame([("2026-07-19T12:00:00+00:00", 5000.0)])
    shifted = PricePredictor()._build_shifted_dataset(df, horizon=3)
    assert shifted.empty


def test_a_frame_without_a_departure_time_is_refused():
    """Pooling departures would silently relabel rows, so the missing key is an error.

    `price_at_lag` degrades to whichever curve keys are present, which is right
    for a feature that reports NaN. It is not right for the label: a frame keyed
    on route, airline and departure date alone treats every aircraft that day as
    one price history, and the resulting label is another departure's later fare
    with nothing to indicate it.

    The column dropped is `departure_time`, the per-flight component of
    `BOOKING_CURVE_KEYS` since 2026-09-03. Dropping `flight_number`, as this test
    used to, no longer removes anything the join reads, so the expected `ValueError`
    would not be raised and the test would fail while the pooling it guards against
    went unchecked.
    """
    df = _frame([
        ("2026-07-19T12:00:00+00:00", 5000.0),
        ("2026-07-22T12:00:00+00:00", 5500.0),
    ]).drop(columns=["departure_time"])

    with pytest.raises(ValueError, match="departure_time"):
        PricePredictor()._build_shifted_dataset(df, horizon=3)
