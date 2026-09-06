"""The label must land on a real observation, within the stated tolerance.

Previously this test asserted `row["recorded_date"].isoformat() == "2026-07-19"`
against a column the old `_build_shifted_dataset` synthesised while doing a
calendar-date join. The join is now an as-of match on the observation timestamp,
so what matters is *which observation* was matched and how stale it was allowed
to be — `lag_tolerance_days(h)`, not a date string.
"""

import pytest
import sys
import os
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.ml.price_model import PricePredictor
from backend.services.booking_curve_definition import lag_tolerance_days

CURVE = {
    "origin_code": "DEL",
    "destination_code": "BOM",
    "airline_code": "AI",
    "departure_time": "06:10",
    "departure_date": "2026-08-26",
}


def _frame(observations):
    return pd.DataFrame([
        {**CURVE, "recorded_at": ts, "price": price} for ts, price in observations
    ])


def test_future_target_alignment_joins():
    """Record at T is labelled with the earliest observation at or after T + 1d."""
    df = _frame([
        ("2026-07-19T12:00:00+00:00", 6000.0),
        ("2026-07-20T12:00:00+00:00", 6200.0),
    ])

    shifted = PricePredictor()._build_shifted_dataset(df, horizon=1)

    # Only the 07-19 row has an observation a day later; the 07-20 row has no
    # future and is dropped rather than labelled with itself.
    assert len(shifted) == 1
    row = shifted.iloc[0]
    assert row["price"] == 6000.0
    assert row["target_price"] == 6200.0
    assert pd.Timestamp(row["recorded_at"]) == pd.Timestamp("2026-07-19T12:00:00+00:00")


def test_match_must_be_inside_the_lag_tolerance():
    """An observation later than T + h + tolerance does not label the row.

    At horizon 1 the tolerance is 0.5 days, so a fare seen 2 days later is not
    "tomorrow's price". The old calendar-date join had no such bound: any row on
    the target date matched, and a horizon expressed in days matched whatever the
    ingestion cadence happened to produce.
    """
    assert lag_tolerance_days(1) == 0.5

    inside = _frame([
        ("2026-07-19T12:00:00+00:00", 6000.0),
        ("2026-07-20T20:00:00+00:00", 6200.0),   # T+1d8h, within [T+1d, T+1d12h]
    ])
    outside = _frame([
        ("2026-07-19T12:00:00+00:00", 6000.0),
        ("2026-07-21T12:00:00+00:00", 6200.0),   # T+2d, beyond the tolerance
    ])

    assert len(PricePredictor()._build_shifted_dataset(inside, horizon=1)) == 1
    assert PricePredictor()._build_shifted_dataset(outside, horizon=1).empty


def test_an_earlier_observation_never_labels_a_later_row():
    """The match is forward-only: the label is always in the row's future."""
    df = _frame([
        ("2026-07-19T12:00:00+00:00", 6000.0),
        ("2026-07-20T12:00:00+00:00", 6200.0),
        ("2026-07-21T12:00:00+00:00", 6400.0),
    ])
    shifted = PricePredictor()._build_shifted_dataset(df, horizon=1)
    for _, row in shifted.iterrows():
        assert row["target_price"] > row["price"], (
            "on a strictly rising curve every forward label must exceed its row; "
            "a lower value means the join looked backwards"
        )
