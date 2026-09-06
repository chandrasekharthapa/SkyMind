"""Tests for time-series validation — no future leakage into training folds.

Two of the tests this file used to contain did not test what their names said.

`test_cv_folds_no_overlap` never called the cross-validator. It re-derived
`fold_size = max(1, n // (n_folds + 1))` inside the test body, sliced the frame
itself, and asserted that its own slices were in order — so it passed whatever
`TimeSeriesCrossValidator` did, including the rolling-window arithmetic that
produced no folds at all. It now reads the fold boundaries out of the report the
validator publishes.

`test_cv_report_avg_mae_is_positive` wrapped its only assertion in
`if not np.isnan(avg_mae)`, which is exactly the state the validator reaches when
it scores zero folds. A run that silently produced nothing satisfied it. Zero
folds is now the failure it should always have been.

The estimator here is a local two-line linear fit rather than `XGBRegressor`,
because none of this is about gradient boosting: the questions are which rows
ended up in which fold and when they were observed. It lives in
`backend/tests/linear_estimator.py` so this module and `test_cross_validation.py`
exercise the validator through the same object, and it exposes `get_params` so
`sklearn.base.clone` can rebuild it per fold, which is the only interface the
validator asks of a model.
"""
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from backend.ml.cross_validation import TimeSeriesCrossValidator
from backend.ml.dataset_splitter import DatasetSplitter
from backend.services.booking_curve_definition import lag_tolerance_days
from backend.tests.linear_estimator import LinearOnFirstFeature


def _make_df(n: int = 300, freq_hours: int = 1, key: str = "recorded_at") -> pd.DataFrame:
    base = datetime(2026, 1, 1)
    return pd.DataFrame([
        {
            key: (base + timedelta(hours=i * freq_hours)).isoformat(),
            "price_idx": float(i),
            "target_price": float(1000 + i * 5),
        }
        for i in range(n)
    ])


def _validate(df, **over):
    args = dict(n_folds=3, strategy="expanding",
                feature_set_version="feature_set_v1", forecast_horizon=3,
                min_train_rows=20)
    args.update(over)
    return TimeSeriesCrossValidator().validate(
        df, LinearOnFirstFeature(), ["price_idx"], "target_price", **args)


def test_splitter_train_precedes_val():
    """Splitter: all training timestamps must precede all validation timestamps."""
    df = _make_df(200)
    splitter = DatasetSplitter()
    split = splitter.split(df, target_col="target_price", test_size=0.2)
    train_max = pd.to_datetime(split.X_train["recorded_at"]).max()
    val_min = pd.to_datetime(split.X_val["recorded_at"]).min()
    assert train_max <= val_min, "Future data leaked into training set!"


def test_cv_folds_no_overlap():
    """Each fold's validation rows must all have been observed after its training rows.

    Read off the report rather than recomputed here. The point of the report
    carrying `fold_windows` is that this assertion becomes a statement about the
    validator instead of a statement about arithmetic copied out of it.
    """
    report = _validate(_make_df(300))
    scored = [w for w in report.fold_windows if w["scored"]]
    assert len(scored) == 3, report.fold_windows

    for window in scored:
        train_end = pd.Timestamp(window["train_end"])
        val_start = pd.Timestamp(window["val_start"])
        assert train_end < val_start, (
            f"Fold {window['fold']}: train_end={train_end} is not before "
            f"val_start={val_start} — future leaked!"
        )
        assert window["boundary_is_strict"] is True

    assert report.boundary_is_strict_in_every_fold is True
    # The folds advance: each one validates on later rows than the one before.
    starts = [pd.Timestamp(w["val_start"]) for w in scored]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


def test_cv_report_records_a_nonzero_number_of_folds():
    """Zero folds is a failure, not a reason to skip the assertion.

    The previous version of this test guarded its assertion behind
    `if not np.isnan(avg_mae)`, and an all-NaN average is precisely what a run
    that scored no folds publishes.
    """
    report = _validate(_make_df(300))
    assert report.n_folds == 3
    assert len(report.fold_metrics) == 3
    avg_mae = report.avg_metrics["mae"]
    assert not np.isnan(avg_mae), "cross-validation scored no fold at all"
    assert avg_mae >= 0.0


def test_splitter_test_fraction_respected():
    df = _make_df(100)
    splitter = DatasetSplitter()
    split = splitter.split(df, target_col="target_price", test_size=0.2)
    # Allow ±1 row of rounding
    expected_val = 100 * 0.2
    assert abs(split.val_rows - expected_val) <= 1


# ── The per-fold label embargo ────────────────────────────────────────────────

def test_every_fold_boundary_is_embargoed_not_just_the_last():
    """A fold count is a leak count: `n_folds` boundaries need `n_folds` purges.

    Ordering by observation time puts each fold's training *features* before its
    validation slice. The labels are a different matter: the target for a row
    observed at `t` is a fare recorded at or after `t + h`, so without a purge
    every one of the boundaries trains on prices drawn from its own validation
    window. That is why cross-validated error used to be able to come out below
    holdout error and read as a good sign.
    """
    embargo = 3.0 + lag_tolerance_days(3)      # 4.5 days
    df = _make_df(300, freq_hours=6)           # 75 days of observations
    report = _validate(df, embargo_days=embargo)

    scored = [w for w in report.fold_windows if w["scored"]]
    assert scored, report.fold_windows
    assert report.embargo_days == embargo
    for window in scored:
        assert window["rows_purged_by_embargo"] > 0, window
        assert window["gap_days"] >= embargo, window
        assert window["embargo_is_effective"] is True, window
        assert (pd.Timestamp(window["val_start"])
                - pd.Timestamp(window["train_end"])) >= pd.Timedelta(days=embargo)
        assert (pd.Timestamp(window["train_end"])
                <= pd.Timestamp(window["embargo_cutoff"]))
    assert report.embargo_is_effective_in_every_fold is True


def test_the_embargo_only_ever_removes_training_rows():
    """Validation slices are the measurement; purging them would discard it."""
    df = _make_df(300, freq_hours=6)
    plain = _validate(df)
    purged = _validate(df, embargo_days=3.0 + lag_tolerance_days(3))

    assert [w["val_rows"] for w in purged.fold_windows] == \
           [w["val_rows"] for w in plain.fold_windows]
    for before, after in zip(plain.fold_windows, purged.fold_windows):
        assert after["train_rows_before_embargo"] == before["train_rows"]
        assert after["train_rows"] < before["train_rows"]
        assert (after["train_rows_before_embargo"] - after["train_rows"]
                == after["rows_purged_by_embargo"])


# ── The rolling window ────────────────────────────────────────────────────────

def test_the_rolling_window_is_one_fold_wide():
    """`train_end = train_start + fold_size`, not a fraction of it.

    The expression in force was `train_start + fold_size * (n_folds - 1) //
    n_folds`, which is narrower than one fold at every `n_folds` — 50 rows where
    `fold_size` was 75. The dead line directly above it,
    `window = fold_size * n_folds // n_folds  # rolling window = fold_size`,
    computed the intended width and was never read.
    """
    n, n_folds = 300, 3
    fold_size = n // (n_folds + 1)             # 75
    report = _validate(_make_df(n), strategy="rolling", n_folds=n_folds)

    scored = [w for w in report.fold_windows if w["scored"]]
    assert len(scored) == n_folds
    assert [w["train_rows"] for w in scored] == [fold_size] * n_folds
    assert [w["val_rows"] for w in scored] == [fold_size] * n_folds
    # A window, not an expansion: each fold's training slice starts later.
    starts = [pd.Timestamp(w["train_start"]) for w in scored]
    assert starts == sorted(starts) and len(set(starts)) == n_folds


def test_rolling_with_one_fold_produces_a_fold():
    """`fold_size * 0 // 1 == 0`, so this used to score nothing and report NaN."""
    report = _validate(_make_df(200), strategy="rolling", n_folds=1)
    assert report.n_folds == 1
    assert not np.isnan(report.avg_metrics["mae"])


def test_the_expanding_window_grows_and_keeps_its_start():
    report = _validate(_make_df(300), strategy="expanding", n_folds=3)
    scored = [w for w in report.fold_windows if w["scored"]]
    assert len(scored) == 3
    assert len({w["train_start"] for w in scored}) == 1, "expanding must not drop rows"
    rows = [w["train_rows"] for w in scored]
    assert rows == sorted(rows) and len(set(rows)) == 3


# ── The shared observation axis ───────────────────────────────────────────────

def test_the_validator_and_the_splitter_order_rows_the_same_way():
    """One corpus, one ordering.

    The two used to disagree: this validator sorted on `recorded_at`, the holdout
    split resolved `search_timestamp` first. Different orderings cut different
    folds, so the cross-validated metric and the holdout metric in one training
    report were not measurements of the same experiment.
    """
    df = _make_df(200, key="search_timestamp")
    # `recorded_at` present but deliberately reversed, so a validator reading it
    # instead of the shared axis produces a visibly different order.
    df["recorded_at"] = list(reversed(df["search_timestamp"].tolist()))

    report = _validate(df, n_folds=2)
    split = DatasetSplitter().split(df, target_col="target_price", test_size=0.2)

    assert report.timestamp_column == "search_timestamp"
    assert split.timestamp_column == "search_timestamp"
    assert report.boundary_is_strict_in_every_fold is True
    # Read off the frames, not the records: the first training row of the first
    # fold is the earliest observation in the corpus under either object's sort.
    first_fold = next(w for w in report.fold_windows if w["scored"])
    assert pd.Timestamp(first_fold["train_start"]) == \
           pd.to_datetime(df["search_timestamp"], utc=True).min()
    assert split.train_date_min == first_fold["train_start"]


def test_rows_with_no_parseable_timestamp_are_dropped_and_counted():
    """They used to sort to the end, i.e. into the last fold's validation slice.

    `NaT` sorts last under `sort_values`, so every row whose timestamp could not
    be parsed was handed to the slice whose entire meaning is "observed later than
    the training rows".
    """
    df = _make_df(120)
    df.loc[df.index[:10], "recorded_at"] = "not-a-timestamp"

    report = _validate(df, n_folds=2, min_train_rows=10)
    assert report.rows_dropped_no_timestamp == 10
    scored = [w for w in report.fold_windows if w["scored"]]
    assert scored
    assert sum(w["val_rows"] for w in scored) <= 110
    for window in scored:
        assert window["train_start"] is not None
        assert window["val_start"] is not None


# ── What the report says when it measured nothing ─────────────────────────────

def test_a_fold_that_could_not_be_scored_says_why():
    """It used to `continue` and leave no trace.

    A report with `n_folds=0` and all-NaN averages gave an operator nothing to
    act on: too few rows, no usable feature column, and an embargo that consumed
    the training slice all looked identical from the outside.
    """
    report = _validate(_make_df(60), n_folds=3, min_train_rows=200)
    assert report.n_folds == 0
    assert len(report.fold_windows) == 3
    for window in report.fold_windows:
        assert window["scored"] is False
        assert "min_train_rows=200" in window["skip_reason"]
        # The window is still described, so the reason can be checked against it.
        assert window["train_rows"] < 200
        assert window["train_start"] is not None


def test_an_embargo_that_starves_a_fold_names_the_embargo_in_the_reason():
    report = _validate(_make_df(300, freq_hours=1), n_folds=3, embargo_days=400.0)
    assert report.n_folds == 0
    for window in report.fold_windows:
        assert window["train_rows"] == 0
        assert window["rows_purged_by_embargo"] == window["train_rows_before_embargo"]
        assert "400.0d embargo purged" in window["skip_reason"]
        assert window["gap_days"] is None
        assert window["embargo_is_effective"] is False


def test_no_scored_fold_means_the_report_claims_nothing():
    """`all([])` is True, and a vacuous claim of cleanliness is the worst outcome."""
    report = _validate(_make_df(60), n_folds=3, min_train_rows=200)
    assert report.n_folds == 0
    assert report.boundary_is_strict_in_every_fold is False
    assert report.embargo_is_effective_in_every_fold is False
    assert np.isnan(report.avg_metrics["mae"])


def test_the_embargo_claim_is_false_when_no_embargo_was_asked_for():
    """Not "clean by default": with no embargo, the labels were never separated."""
    report = _validate(_make_df(300))
    assert report.n_folds == 3
    assert report.boundary_is_strict_in_every_fold is True
    assert report.embargo_is_effective_in_every_fold is False
    assert report.embargo_days == 0.0


def test_unknown_strategy_and_missing_time_column_are_refused():
    df = _make_df(100)
    with pytest.raises(ValueError, match="Unknown validation_strategy"):
        _validate(df, strategy="bad_strategy")
    with pytest.raises(ValueError, match="No time column"):
        _validate(df.drop(columns=["recorded_at"]))
    with pytest.raises(ValueError, match="target_price"):
        _validate(df.drop(columns=["target_price"]))
