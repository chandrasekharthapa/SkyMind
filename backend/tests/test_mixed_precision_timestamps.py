"""Every timestamp column in this project holds two shapes, not one.

Postgres renders a `timestamptz` without the microseconds field when that field
is zero, and rows written from Python go through `datetime.isoformat()`, which
does the same. So `search_timestamp`, `recorded_at` and `snapshot_time` all mix

    2026-08-15T10:00:00.123456+00:00
    2026-08-15T10:00:01+00:00

`pd.to_datetime` without an explicit format infers one format from the first
non-null element and applies it to the whole column. With `errors="coerce"` every
element of the other shape becomes `NaT`; with the default `errors="raise"` the
call dies with `time data ... doesn't match format`. Measured on pandas 2.3.3,
the two-element list above loses one row to `NaT`.

That is why this project passes `format="ISO8601"` at every such call site, and
why the loss was invisible before: the `UserWarning: Could not infer format`
pandas used to emit fired on the path where inference *failed* and per-element
parsing then got every row right. The lossy path was the silent one.

These cases pin the consequence rather than the call. Each one asserts that a
frame holding both shapes yields a value for both rows — an observation time, a
booking horizon, a snapshot sequence number. A regression to format inference
turns each of them into a null for one row.
"""

import pandas as pd
import pytest

from backend.dataset.snapshot import compute_snapshot_sequences
from backend.services.booking_curve_definition import (
    ORDERING_TIMESTAMP_KEY,
    booking_horizon_days,
    observed_at_of_record,
    ordering_timestamps,
)

# Same instant to the second, differing only in whether the microseconds field
# is present. Both are valid ISO-8601 and both come out of this project's own
# writers.
WITH_MICROS = "2026-08-15T10:00:00.123456+00:00"
WITHOUT_MICROS = "2026-08-15T10:00:01+00:00"
MIXED = [WITH_MICROS, WITHOUT_MICROS]


def test_pandas_still_loses_a_row_to_format_inference():
    """The premise of every case below, asserted rather than assumed.

    If a future pandas stops inferring a single format, this fails and the rest
    of the module becomes redundant — which is worth knowing explicitly instead
    of discovering that the other cases have quietly stopped testing anything.
    """
    inferred = pd.to_datetime(pd.Series(MIXED), errors="coerce", utc=True)
    assert inferred.isna().sum() == 1, (
        "format inference no longer drops a mixed-precision element; the "
        "format= arguments this module protects may no longer be load-bearing")


def test_the_shared_observation_axis_keeps_both_shapes():
    df = pd.DataFrame({ORDERING_TIMESTAMP_KEY: MIXED})
    times = ordering_timestamps(df)

    assert times.notna().all(), f"lost an observation time: {list(times)}"
    assert times.iloc[1] - times.iloc[0] == pd.Timedelta(seconds=1) - \
        pd.Timedelta(microseconds=123456)


def test_the_row_level_and_frame_level_definitions_agree_on_both_shapes():
    """`observed_at_of_record` is the single-row form of `ordering_timestamps`.

    They are two implementations of one definition, so a format applied to only
    one of them would make the serving path and the training path disagree about
    which observations exist.
    """
    df = pd.DataFrame({ORDERING_TIMESTAMP_KEY: MIXED})
    frame_level = ordering_timestamps(df)

    for i, raw in enumerate(MIXED):
        row_level = observed_at_of_record({ORDERING_TIMESTAMP_KEY: raw})
        assert row_level is not None, f"row-level parse lost {raw!r}"
        assert row_level == frame_level.iloc[i]


def test_a_horizon_is_returned_for_both_shapes():
    """A NaT observation time is not a horizon of zero — it is no horizon.

    So a row lost to format inference is dropped from the supervised label and
    from every lag feature, and the loss shows up only as a smaller dataset.
    """
    df = pd.DataFrame({
        ORDERING_TIMESTAMP_KEY: MIXED,
        "departure_date": ["2026-08-20", "2026-08-20"],
    })
    horizons = booking_horizon_days(df)

    assert horizons.notna().all(), f"lost a booking horizon: {list(horizons)}"
    assert list(horizons) == [5.0, 5.0]


def test_a_mixed_departure_date_column_still_yields_a_horizon():
    """`departure_date` mixes a bare date with a full timestamp, not two precisions.

    `format="ISO8601"` alone returns *object* dtype for that mix, which makes the
    `.dt` access inside `booking_horizon_days` raise; `utc=True` is what keeps the
    result a datetime column. Both halves of that pair are asserted here.
    """
    df = pd.DataFrame({
        ORDERING_TIMESTAMP_KEY: MIXED,
        "departure_date": ["2026-08-20", "2026-08-21T00:00:00+00:00"],
    })
    horizons = booking_horizon_days(df)

    assert horizons.notna().all(), f"lost a booking horizon: {list(horizons)}"
    assert list(horizons) == [5.0, 6.0]


def test_every_snapshot_gets_a_sequence_number():
    """`snapshot_time` is written by `attach_snapshot_metadata` with `isoformat()`.

    So this column is guaranteed to hold both shapes whenever any observation
    lands on a whole second, and a row that cannot be ordered gets no sequence
    number at all.
    """
    df = pd.DataFrame({
        "itinerary_id": ["itin_1", "itin_1"],
        "snapshot_time": MIXED,
    })
    out = compute_snapshot_sequences(df)

    assert "snapshot_sequence" in out.columns
    sequences = out["snapshot_sequence"].dropna().tolist()
    assert sorted(sequences) == [1, 2], (
        f"expected both snapshots numbered, got {out['snapshot_sequence'].tolist()}")


@pytest.mark.parametrize("column", [ORDERING_TIMESTAMP_KEY, "recorded_at"])
def test_both_columns_of_the_axis_are_parsed_the_same_way(column):
    """`recorded_at` is the fallback half of the axis and comes straight from
    Postgres, which is itself a source of both shapes."""
    times = ordering_timestamps(pd.DataFrame({column: MIXED}))
    assert times.notna().all(), f"{column} lost an observation time"
