"""Tests for DatasetSplitter — chronological safety guarantees."""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from backend.ml.dataset_splitter import DatasetSplitter
from backend.services.booking_curve_definition import lag_tolerance_days


def _make_df(n: int = 200) -> pd.DataFrame:
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n):
        rows.append({
            "recorded_at": (base + timedelta(days=i)).isoformat(),
            "price": float(1000 + i * 10),
            "target_price": float(1100 + i * 10),
            "feature_a": float(i),
            "feature_b": float(n - i),
        })
    return pd.DataFrame(rows)


def test_splitter_produces_non_empty_sets():
    df = _make_df(200)
    splitter = DatasetSplitter()
    split = splitter.split(df, target_col="target_price", test_size=0.2)
    assert split.train_rows > 0
    assert split.val_rows > 0


def test_splitter_never_shuffles():
    """Train max date must be strictly before val min date."""
    df = _make_df(200)
    splitter = DatasetSplitter()
    split = splitter.split(df, target_col="target_price", test_size=0.2)
    train_max = pd.to_datetime(split.train_date_max)
    val_min = pd.to_datetime(split.val_date_min)
    assert train_max <= val_min, (
        f"DatasetSplitter leaked future data: "
        f"train_max={train_max} > val_min={val_min}"
    )


def test_splitter_row_count_matches():
    df = _make_df(100)
    splitter = DatasetSplitter()
    split = splitter.split(df, target_col="target_price", test_size=0.2)
    assert split.train_rows + split.val_rows == 100


def test_splitter_raises_on_empty_df():
    splitter = DatasetSplitter()
    with pytest.raises(ValueError, match="empty"):
        splitter.split(pd.DataFrame(), target_col="target_price")


def test_splitter_raises_on_missing_target():
    df = _make_df(50)
    splitter = DatasetSplitter()
    with pytest.raises(ValueError, match="not found"):
        splitter.split(df, target_col="nonexistent_col")


def test_splitter_raises_on_no_time_column():
    df = pd.DataFrame({"price": [1, 2, 3], "target_price": [2, 3, 4]})
    splitter = DatasetSplitter()
    with pytest.raises(ValueError, match="time column"):
        splitter.split(df, target_col="target_price")


def test_splitter_x_train_excludes_target():
    df = _make_df(100)
    splitter = DatasetSplitter()
    split = splitter.split(df, target_col="target_price", test_size=0.2)
    assert "target_price" not in split.X_train.columns
    assert "target_price" not in split.X_val.columns


# ── The label embargo ─────────────────────────────────────────────────────────
#
# Ordering by observation time separates the folds' *features*. It says nothing
# about the training rows' labels: `attach_future_target` gives a row observed at
# `t` the earliest fare on its booking curve at or after `t + h`, accepted up to
# `t + h + lag_tolerance_days(h)`. A training row observed inside that window of
# the first validation observation therefore carries a price recorded during the
# validation period, and fitting on it consumes the fold it is about to be scored
# against. `embargo_days` drops exactly those rows.

def test_the_embargo_purges_training_rows_whose_labels_reach_validation():
    df = _make_df(100)                          # one observation per day
    width = 3.0 + lag_tolerance_days(3)         # 4.5 days
    splitter = DatasetSplitter()

    plain = splitter.split(df, target_col="target_price", test_size=0.2)
    purged = splitter.split(df, target_col="target_price", test_size=0.2,
                            embargo_days=width)

    assert purged.train_rows_before_embargo == plain.train_rows == 80
    # One observation per day, validation opening on day 80, so the cutoff falls
    # at day 75.5 and days 76-79 go: four rows, not five. The count is asserted
    # rather than derived so that a change to the purge's comparison — `<=` to
    # `<`, or the cutoff moving by a row — shows up here as a number.
    assert purged.rows_purged_by_embargo == 4
    assert purged.train_rows == 76
    assert purged.val_rows == plain.val_rows == 20, "the purge never drops val rows"
    assert purged.gap_days >= width
    assert purged.embargo_is_effective is True
    assert purged.boundary_is_strict is True
    assert (pd.Timestamp(purged.val_date_min) - pd.Timestamp(purged.train_date_max)
            >= pd.Timedelta(days=width))
    # The training fold ends earlier than it did without the embargo; the record
    # keeps both so the difference is auditable from the artifact alone.
    assert pd.Timestamp(purged.train_date_max) < pd.Timestamp(plain.train_date_max)


def test_a_wider_embargo_purges_more_and_the_gap_tracks_the_horizon():
    df = _make_df(100)
    splitter = DatasetSplitter()
    widths = [h + lag_tolerance_days(h) for h in (1, 3, 7)]
    assert widths == [1.5, 4.5, 10.5]

    results = [splitter.split(df, target_col="target_price", test_size=0.2,
                              embargo_days=w) for w in widths]
    assert [r.rows_purged_by_embargo for r in results] == [1, 4, 10]
    assert [r.gap_days for r in results] == [2.0, 5.0, 11.0]
    for width, result in zip(widths, results):
        assert result.gap_days >= width
        assert result.embargo_is_effective is True


def test_an_embargo_wider_than_the_corpus_empties_the_training_fold_and_says_so():
    """Refusing to train is the caller's decision; reporting honestly is this one's."""
    split = DatasetSplitter().split(_make_df(100), target_col="target_price",
                                    test_size=0.2, embargo_days=400.0)
    assert split.train_rows == 0
    assert split.rows_purged_by_embargo == 80
    assert split.gap_days is None
    assert split.embargo_is_effective is False
    assert split.boundary_is_strict is False
    assert split.train_date_max is None


def test_the_record_names_the_strategy_it_actually_used():
    df = _make_df(100)
    splitter = DatasetSplitter()
    plain = splitter.split(df, target_col="target_price").to_dict()
    purged = splitter.split(df, target_col="target_price",
                            embargo_days=4.5).to_dict()
    assert plain["strategy"] == "chronological_by_observation_time"
    assert plain["embargo_days"] == 0.0
    assert purged["strategy"] == "chronological_by_observation_time_with_embargo"
    assert purged["embargo_days"] == 4.5
    assert purged["timestamp_column"] == "recorded_at"


# ── The time axis ─────────────────────────────────────────────────────────────

def test_the_split_orders_by_the_search_instant_when_there_is_one():
    """`search_timestamp` is when the fare was observed; `recorded_at` is when the
    row was written. This splitter used to sort on the latter while
    `price_model.chronological_split` sorted on the former, which means the two
    training paths in this repo cut different test folds out of one corpus and
    published metrics that were not comparable.
    """
    df = _make_df(100)
    df["search_timestamp"] = df["recorded_at"]
    # `recorded_at` reversed: a splitter reading it instead of the shared axis
    # produces a visibly different boundary.
    df["recorded_at"] = list(reversed(df["recorded_at"].tolist()))

    split = DatasetSplitter().split(df, target_col="target_price", test_size=0.2)
    assert split.timestamp_column == "search_timestamp"
    observed = pd.to_datetime(df["search_timestamp"], utc=True)
    assert pd.Timestamp(split.train_date_min) == observed.min()
    assert pd.Timestamp(split.val_date_max) == observed.max()
    assert pd.Timestamp(split.train_date_max) < pd.Timestamp(split.val_date_min)


def test_a_row_missing_the_search_instant_falls_back_per_row_not_per_column():
    """One unset `search_timestamp` used to send the whole frame down the fallback.

    `ordering_timestamps` coalesces per row, which matters because the writer does
    the same: `ingestion_controller` resolves a missing `search_timestamp` to
    `recorded_at` before insert. A reader resolving per column disagreed with the
    writer about when a row happened.
    """
    df = _make_df(100)
    df["search_timestamp"] = df["recorded_at"]
    df.loc[df.index[[0, 50, 99]], "search_timestamp"] = None

    split = DatasetSplitter().split(df, target_col="target_price", test_size=0.2)
    assert split.timestamp_column == "search_timestamp"
    assert split.rows_dropped_no_timestamp == 0, "the fallback covered all three"
    assert split.train_rows + split.val_rows == 100


def test_the_sort_is_on_parsed_instants_not_on_the_raw_string():
    """Mixed UTC offsets sort lexicographically into the wrong order.

    `price_history` holds both tz-aware values from Supabase and naive ones from
    CSV loads. Here the second observation carries `+05:30`, so as text it sorts
    after the third while in fact preceding it — and under the old
    `df.sort_values("recorded_at")` it crossed the fold boundary in the wrong
    direction, putting a later observation in training than the earliest
    validation row.
    """
    df = pd.DataFrame({
        "recorded_at": ["2026-01-01T00:00:00+00:00",   # 1st: Jan 1 00:00Z
                        "2026-01-05T00:00:00+05:30",   # 2nd: Jan 4 18:30Z
                        "2026-01-04T20:00:00+00:00",   # 3rd: Jan 4 20:00Z
                        "2026-01-06T00:00:00+00:00"],  # 4th: Jan 6 00:00Z
        "row_id": [1, 2, 3, 4],
        "target_price": [100.0, 200.0, 300.0, 400.0],
    })
    # As text, row 3 sorts before row 2 — the ordering the old code used.
    assert sorted(df["recorded_at"]) != [
        df["recorded_at"][0], df["recorded_at"][1],
        df["recorded_at"][2], df["recorded_at"][3]]

    split = DatasetSplitter().split(df, target_col="target_price", test_size=0.5)
    assert sorted(split.X_train["row_id"]) == [1, 2]
    assert sorted(split.X_val["row_id"]) == [3, 4]
    assert pd.Timestamp(split.train_date_max) < pd.Timestamp(split.val_date_min)


def test_rows_with_no_parseable_timestamp_are_dropped_and_counted():
    """They used to sort to the end, which is the validation fold.

    `NaT` sorts last, so every unorderable row was handed to the fold whose whole
    meaning is "observed after the training data".
    """
    df = _make_df(100)
    df.loc[df.index[:10], "recorded_at"] = "not-a-timestamp"

    split = DatasetSplitter().split(df, target_col="target_price", test_size=0.2)
    assert split.rows_dropped_no_timestamp == 10
    assert split.train_rows + split.val_rows == 90
    assert split.val_rows == 18
    assert pd.Timestamp(split.train_date_max) < pd.Timestamp(split.val_date_min)


def test_no_row_has_a_usable_timestamp():
    df = _make_df(20)
    df["recorded_at"] = "not-a-timestamp"
    with pytest.raises(ValueError, match="parseable observation time"):
        DatasetSplitter().split(df, target_col="target_price")


def test_the_sort_key_never_becomes_a_feature():
    """It is prefixed with `_` so `feature_cols` excludes it by rule, not by name."""
    split = DatasetSplitter().split(_make_df(100), target_col="target_price",
                                    test_size=0.2)
    for frame in (split.X_train, split.X_val):
        assert not [c for c in frame.columns if c.startswith("_")]
        assert "price" in frame.columns, "the persistence baseline needs this"
