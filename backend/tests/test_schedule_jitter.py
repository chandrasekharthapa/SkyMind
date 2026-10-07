"""A daily scrape that runs a little earlier than yesterday's still counts as "a day later".

On the 2026-10-07 export, 18,000 of 33,600 gaps between two observations of the
same flight were 0.90–0.99 days, because the collector does not start at the
same second each day. The label and the lag features accepted only observations
at or beyond exactly t ± n days, so those pairs were discarded: 10,444 one-day
labels instead of 28,698, and 317 training rows after the split.
"""

import pandas as pd

from backend.services.booking_curve_definition import (
    lag_tolerance_days, price_at_horizon, price_at_lag, schedule_jitter_days,
)

FLIGHT = {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
          "departure_time": "06:10", "departure_date": "2026-10-20"}
T0 = pd.Timestamp("2026-10-02T01:30:00Z")


def _pair(gap_days, later_price=5500.0):
    return pd.DataFrame([
        {**FLIGHT, "recorded_at": T0.isoformat(), "price": 5000.0},
        {**FLIGHT, "recorded_at": (T0 + pd.Timedelta(days=gap_days)).isoformat(),
         "price": later_price},
    ])


def test_a_rescrape_a_few_hours_short_of_a_day_is_the_one_day_label_and_lag():
    df = _pair(0.95)
    assert price_at_horizon(df, 1).iloc[0] == 5500.0
    assert price_at_lag(df, 1).iloc[1] == 5000.0


def test_the_early_edge_is_bounded():
    assert schedule_jitter_days(1) == 0.25 and schedule_jitter_days(0.5) == 0.125
    df = _pair(0.70)            # too soon to be "a day later"
    assert pd.isna(price_at_horizon(df, 1).iloc[0])
    assert pd.isna(price_at_lag(df, 1).iloc[1])


def test_the_late_edge_and_so_the_embargo_width_is_unchanged():
    late_ok = 1 + lag_tolerance_days(1) - 0.01
    too_late = 1 + lag_tolerance_days(1) + 0.01
    assert price_at_horizon(_pair(late_ok), 1).iloc[0] == 5500.0
    assert pd.isna(price_at_horizon(_pair(too_late), 1).iloc[0])
