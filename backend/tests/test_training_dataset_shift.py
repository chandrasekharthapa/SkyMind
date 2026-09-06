"""The label must stay on the booking curve it labels.

The old target join appended `flight_number` to its keys only inside
`if "flight_number" in target_df.columns`, and `target_df` came from a column
selection that never included it — so the branch was dead and every label was
matched on route, airline and departure date alone. On a route where one airline
flies several times a day, that means the "future price of this flight" was
routinely a different aircraft's fare.

The per-flight component is `departure_time` as of 2026-09-03, not `flight_number`:
Google Flights publishes no flight number, so keying on it left the column NULL on
every real row and reproduced the same pooling the dead branch caused. This fixture
therefore separates its two curves by departure time. Keyed on flight numbers it would
now pool them, and both tests below would compare a pooled history against itself.

The fixture is the minimum that can detect a crossed label: two departures whose
curves move in opposite directions, so a crossed label is not merely a different
number but a number of the wrong sign.
"""

import pytest
import sys
import os
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.ml.price_model import PricePredictor

RISING = {"departure_time": "06:10", "prices": [5000.0, 5500.0, 6000.0]}
FALLING = {"departure_time": "19:45", "prices": [9000.0, 8400.0, 7800.0]}
STAMPS = ["2026-07-19T12:00:00+00:00", "2026-07-22T12:00:00+00:00", "2026-07-25T12:00:00+00:00"]


def _frame():
    rows = []
    for curve in (RISING, FALLING):
        for ts, price in zip(STAMPS, curve["prices"]):
            rows.append({
                "origin_code": "DEL",
                "destination_code": "BOM",
                "airline_code": "6E",
                "departure_time": curve["departure_time"],
                "departure_date": "2026-08-26",
                "recorded_at": ts,
                "price": price,
            })
    # Interleaved, so a join that ignores the departure time sees one alternating
    # price history rather than two monotone ones.
    return pd.DataFrame(rows).sample(frac=1.0, random_state=7).reset_index(drop=True)


def test_training_dataset_shift():
    """Each row is labelled with its own departure's fare three days later."""
    shifted = PricePredictor()._build_shifted_dataset(_frame(), horizon=3)

    # Two labellable rows per curve: the last observation of each has no future.
    assert len(shifted) == 4

    for _, row in shifted.iterrows():
        assert row["target_price"] != row["price"]
        if row["departure_time"] == RISING["departure_time"]:
            assert row["target_price"] in (5500.0, 6000.0)
            assert row["target_price"] > row["price"]
        else:
            assert row["target_price"] in (8400.0, 7800.0)
            assert row["target_price"] < row["price"]


def test_the_two_curves_never_exchange_labels():
    """No label taken from the rising curve appears on the falling one."""
    shifted = PricePredictor()._build_shifted_dataset(_frame(), horizon=3)
    rising_fares = set(RISING["prices"])
    falling_fares = set(FALLING["prices"])

    by_curve = shifted.groupby("departure_time")["target_price"].apply(set).to_dict()
    assert by_curve[RISING["departure_time"]] <= rising_fares
    assert by_curve[FALLING["departure_time"]] <= falling_fares
    assert not (by_curve[RISING["departure_time"]] & falling_fares)
    assert not (by_curve[FALLING["departure_time"]] & rising_fares)


def test_row_order_does_not_change_the_labels():
    """The join sorts what it needs to; a shuffled frame gets identical labels."""
    predictor = PricePredictor()
    df = _frame()
    a = predictor._build_shifted_dataset(df, horizon=3)
    b = predictor._build_shifted_dataset(
        df.sample(frac=1.0, random_state=99).reset_index(drop=True), horizon=3
    )
    key = ["departure_time", "price", "target_price"]
    assert (
        a[key].sort_values(key).reset_index(drop=True)
        .equals(b[key].sort_values(key).reset_index(drop=True))
    )
