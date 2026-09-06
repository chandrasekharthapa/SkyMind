"""An observation with no curve identity is labelled by nothing and labels nothing.

`curve_identity_is_complete` states the contract: "callers must treat False as
'this observation has no curve'". `curve_window_definition` honoured it. The
as-of join underneath `price_at_horizon` and `price_at_lag` did not, and the
consequence is not a degraded feature — it is a supervised label taken from a
different flight.

The mechanism is `pd.merge_asof(by=keys)`, which factorises the key columns; a
null factorises to a value that matches other nulls. So a route/airline/date with
five NULL `departure_time` rows is one group, and the earliest row is handed the
latest row's fare as "the price 3 days from now".

Why this matters on this corpus specifically: migration 001 adds `departure_time`
with no default and no backfill. Every one of the 32,709 pre-migration rows would
have held NULL the moment the migration was applied — the column present, so
`attach_future_target`'s missing-column guard silent, and the identity mask
returning False for all of them while the label came back populated anyway.
Applying the migration was the trigger, not the fix.
"""

import pytest
import sys
import os
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.booking_curve_definition import (
    attach_future_target,
    curve_identity_mask,
    lag_tolerance_days,
    price_at_lag,
)

ROUTE = {
    "origin_code": "DEL",
    "destination_code": "BOM",
    "airline_code": "6E",
    "departure_date": "2026-08-26",
}

EARLY = "2026-07-01T09:00:00+00:00"
LATE = "2026-07-04T09:00:00+00:00"


def _two_flights(departure_times):
    """Two distinct departures on one route/airline/date, each seen twice.

    The fares are far apart (₹5,000-ish and ₹9,000-ish) so that a cross-flight
    match is unmistakable in the assertion rather than a plausible-looking number.
    """
    a, b = departure_times
    return pd.DataFrame([
        {**ROUTE, "departure_time": a, "recorded_at": EARLY, "price": 5000.0},
        {**ROUTE, "departure_time": b, "recorded_at": EARLY, "price": 9000.0},
        {**ROUTE, "departure_time": a, "recorded_at": LATE, "price": 5300.0},
        {**ROUTE, "departure_time": b, "recorded_at": LATE, "price": 9400.0},
    ])


def test_tolerance_admits_the_match_these_cases_depend_on():
    """Guard the fixture: at h=3 an observation 3 days later is inside tolerance.

    Every negative assertion below claims "no label". That claim is only evidence
    of the identity gate if a label would otherwise have been produced, so the
    arithmetic that makes the match admissible is asserted first. Without this,
    tightening `lag_tolerance_days` would turn the whole module green for the
    wrong reason.
    """
    assert lag_tolerance_days(3) == 1.5
    labelled = attach_future_target(_two_flights(("06:10", "21:45")), horizon=3)
    assert len(labelled) == 2


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_null_departure_time_rows_do_not_label_each_other(blank):
    """The regression. Two flights, both unidentified, must produce no label.

    Measured before the fix, with `blank=None`: `curve_identity_mask` returned
    [False, False, False, False] and `attach_future_target` returned two rows, the
    ₹5,000 row carrying `target_price` 9400.0 — the *other* flight's later fare.
    """
    df = _two_flights((blank, blank))

    assert not curve_identity_mask(df).any(), (
        "fixture precondition: a blank departure_time is not an identity"
    )

    labelled = attach_future_target(df, horizon=3)

    assert labelled.empty, (
        "rows with no curve identity were labelled: "
        f"{labelled[['price', 'target_price']].to_dict('records')}. "
        "merge_asof matched null to null and pooled two flights into one curve."
    )


def test_one_blank_key_is_enough_to_disqualify_a_row():
    """Identity is all five keys. A row missing any one of them has no curve.

    The other three rows are fully identified and unaffected: the gate drops rows,
    it does not fail the frame. Asserted because the cheap implementation of this
    fix — returning all-NaN whenever any row is unidentified — would also make the
    test above pass, and would silently stop training on a corpus with one bad row.
    """
    df = _two_flights(("06:10", "21:45"))
    df.loc[0, "airline_code"] = None

    assert list(curve_identity_mask(df)) == [False, True, True, True]

    labelled = attach_future_target(df, horizon=3)

    # Row 0 had the only early observation of the 06:10 flight, so that flight now
    # has no labelled row at all. Row 1 (21:45, early) still matches row 3.
    assert len(labelled) == 1
    assert labelled.iloc[0]["price"] == 9000.0
    assert labelled.iloc[0]["target_price"] == 9400.0


def test_identified_flights_are_labelled_from_their_own_curve():
    """The positive control, and the reason the gate is not just "return NaN".

    Distinct departure times make two curves out of the same route, airline and
    date. Each early row must take its own flight's later fare — 5000 to 5300 and
    9000 to 9400 — and the late rows have no future within tolerance, so they are
    dropped rather than labelled with themselves.
    """
    labelled = attach_future_target(_two_flights(("06:10", "21:45")), horizon=3)

    pairs = sorted(
        (row["price"], row["target_price"]) for _, row in labelled.iterrows()
    )
    assert pairs == [(5000.0, 5300.0), (9000.0, 9400.0)], (
        "a label crossed between the 06:10 and 21:45 departures"
    )


def test_the_lag_features_honour_the_same_gate():
    """`price_at_lag` and `price_at_horizon` must agree on which rows have a curve.

    They share `_price_at_offset`, so this is a guard against someone applying the
    identity mask in one wrapper and not the other. A feature that pools two
    flights and a label that does not is train/serve skew produced from one frame.
    """
    identified = price_at_lag(_two_flights(("06:10", "21:45")), 3)
    unidentified = price_at_lag(_two_flights((None, None)), 3)

    # Backward lookup: the late rows see their own flight's early fare.
    assert sorted(v for v in identified.dropna()) == [5000.0, 9000.0]
    assert unidentified.isna().all(), (
        "unidentified rows received a lag feature from another flight's curve"
    )


def test_a_frame_with_no_departure_time_column_still_raises():
    """The absent-column path is unchanged, and says which column is missing.

    `_price_at_offset` would now return all-NaN for such a frame, which is honest
    but reads to a caller as "no data". `attach_future_target` keeps raising so
    the caller hears "no fifth key" instead.
    """
    df = _two_flights(("06:10", "21:45")).drop(columns=["departure_time"])

    with pytest.raises(ValueError) as excinfo:
        attach_future_target(df, horizon=3)

    # Asserted on the value rather than left to `match=`, because the message
    # naming the offending column is the whole point of raising here instead of
    # returning the empty frame the join would now produce on its own.
    assert "departure_time" in str(excinfo.value)
