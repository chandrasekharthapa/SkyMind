"""Dataset Splitter.

Chronological-only dataset splitting for time-series model training, with a label
embargo. Never shuffles.

Three things were wrong with the version this replaces, and all three were
invisible from the outside because the row counts and the class name did not
change:

1. *A different time axis from the other training path.* `SORT_COLS` was
   `["recorded_at", "recorded_date"]`, so this splitter ordered by insert time
   while `price_model.chronological_split` ordered by
   `booking_curve_definition.ORDERING_TIMESTAMP_KEY` — the search instant, which
   is when the fare was actually observed. Two training paths in one repo
   disagreeing about when a row happened means their test folds are not the same
   experiment, and the metric each publishes is not comparable with the other's.
   Both now resolve the axis through `ordering_timestamps`, which coalesces per
   row rather than per column; see its docstring for why that distinction is
   load-bearing on this corpus.

2. *Sorting the raw column.* `df.sort_values("recorded_at")` on a column of ISO
   strings is a lexicographic sort. It agrees with chronology only while every
   value has the same format and the same UTC offset — and `price_history` holds
   both tz-aware values from Supabase and naive ones from CSV loads, which sort
   into the wrong order relative to each other. Rows whose timestamp does not
   parse at all sorted to the end and were handed to *validation*, so the fold
   that is supposed to be the future silently collected every unorderable row.
   They are now dropped, and counted.

3. *No embargo.* Ordering by observation time puts every training row's features
   before the validation fold. It says nothing about the training rows' *labels*,
   which are fares observed later on the same booking curve: the label for a row
   observed at `t` is a fare at or after `t + h`, so it can be realised inside the
   validation period. Train on that row and the fit has consumed a price from its
   own validation window. `embargo_days` drops exactly those rows, and the caller
   that knows the horizon supplies the width — `price_model` uses
   `h + lag_tolerance_days(h)`, and `model_trainer` now does the same.

Zero Synthetic Feature Policy: no fabricated rows are added.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from backend.services.booking_curve_definition import (
    ordering_timestamps,
    resolve_ordering_timestamp_column,
)

logger = logging.getLogger(__name__)

# The parsed observation time, added for the sort and removed before the feature
# frame is handed back. Leading underscore because `split` excludes such columns
# from `feature_cols`, so it cannot become an accidental feature.
_SORT_KEY = "_split_observed_at"


@dataclass
class ChronologicalSplit:
    """Result of a single chronological train/validation split."""
    X_train: pd.DataFrame
    X_val: pd.DataFrame
    y_train: pd.Series
    y_val: pd.Series
    train_rows: int
    val_rows: int
    train_date_min: Optional[str]
    train_date_max: Optional[str]
    val_date_min: Optional[str]
    val_date_max: Optional[str]
    # Everything below describes *how* the split was made, and is written into the
    # training report. Defaults are the no-embargo values so the dataclass stays
    # constructible from the five positional groups above.
    timestamp_column: Optional[str] = None
    rows_dropped_no_timestamp: int = 0
    embargo_days: float = 0.0
    train_rows_before_embargo: int = 0
    rows_purged_by_embargo: int = 0
    gap_days: Optional[float] = None
    boundary_is_strict: bool = False
    embargo_is_effective: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """The split's description without the frames — for the training report."""
        return {
            "strategy": ("chronological_by_observation_time_with_embargo"
                         if self.embargo_days > 0.0
                         else "chronological_by_observation_time"),
            "timestamp_column": self.timestamp_column,
            "train_rows": self.train_rows,
            "val_rows": self.val_rows,
            "rows_dropped_no_timestamp": self.rows_dropped_no_timestamp,
            "embargo_days": self.embargo_days,
            "train_rows_before_embargo": self.train_rows_before_embargo,
            "rows_purged_by_embargo": self.rows_purged_by_embargo,
            "train_date_min": self.train_date_min,
            "train_date_max": self.train_date_max,
            "val_date_min": self.val_date_min,
            "val_date_max": self.val_date_max,
            "gap_days": self.gap_days,
            "boundary_is_strict": self.boundary_is_strict,
            "embargo_is_effective": self.embargo_is_effective,
        }


class DatasetSplitter:
    """Splits a feature-engineered DataFrame chronologically.

    Contract:
    - All train rows were observed before all validation rows.
    - No shuffling occurs at any point.
    - The time axis is the one in `booking_curve_definition`: `search_timestamp`
      per row where it parses, `recorded_at` per row where it does not.
    - With `embargo_days > 0`, no surviving training row's label could have been
      realised on or after the first validation observation.
    """

    # Only consulted when the shared axis resolves to nothing. `recorded_date` is
    # a date, not an instant, so it cannot separate two observations made on the
    # same day — which is why it is the last resort rather than a peer.
    FALLBACK_SORT_COLS = ["recorded_date"]

    def split(
        self,
        df: pd.DataFrame,
        target_col: str = "target_price",
        test_size: float = 0.2,
        embargo_days: float = 0.0,
    ) -> ChronologicalSplit:
        """Produce a single chronological train/validation split.

        Args:
            df: Feature-engineered DataFrame with target_col present.
            target_col: Name of the regression target column.
            test_size: Fraction of rows to reserve for validation.
            embargo_days: Width of the label embargo. Training rows observed
                within this many days of the first validation observation are
                dropped, because their labels are fares recorded inside the
                validation period. Pass `h + lag_tolerance_days(h)` for a model
                at horizon `h`; 0.0 reproduces the old behaviour and is not safe
                for a forward-looking label.

        Returns:
            ChronologicalSplit
        """
        if df is None or df.empty:
            raise ValueError("DatasetSplitter received an empty DataFrame.")

        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found in DataFrame.")

        sort_col, observed = self._observation_times(df)
        frame = df.copy()
        frame[_SORT_KEY] = observed
        n_unparseable = int(frame[_SORT_KEY].isna().sum())
        if n_unparseable:
            # Dropped rather than sorted to one end. NaT sorts last, so these used
            # to be handed to the validation fold en masse — the fold whose whole
            # meaning is "later than the training data", filled with rows whose
            # time is unknown.
            logger.warning(
                "[DatasetSplitter] %d of %d row(s) have no parseable observation "
                "time in '%s' and are excluded from both folds. They cannot be "
                "placed on either side of a chronological boundary.",
                n_unparseable, len(frame), sort_col,
            )
            frame = frame[frame[_SORT_KEY].notna()]
        if frame.empty:
            raise ValueError(
                f"DatasetSplitter: no row in the {len(df)}-row frame has a "
                f"parseable observation time in '{sort_col}'."
            )

        # `mergesort` is stable, so equal timestamps keep their input order and the
        # split is reproducible for a given frame.
        df_sorted = frame.sort_values(_SORT_KEY, kind="mergesort").reset_index(drop=True)

        n = len(df_sorted)
        n_val = max(1, int(n * test_size))
        n_train = n - n_val

        if n_train < 1:
            raise ValueError(
                f"DatasetSplitter: insufficient rows after split "
                f"(total={n}, n_train={n_train}, n_val={n_val}). "
                f"Lower test_size or increase minimum_training_rows."
            )

        df_train = df_sorted.iloc[:n_train]
        df_val = df_sorted.iloc[n_train:]

        # The purge, on the training fold only: dropping validation rows would be
        # discarding the measurement rather than the contamination.
        embargo = max(0.0, float(embargo_days))
        train_rows_before = int(len(df_train))
        val_start = df_val[_SORT_KEY].min() if len(df_val) else None
        if embargo > 0.0 and val_start is not None and train_rows_before:
            cutoff = val_start - pd.Timedelta(days=embargo)
            df_train = df_train[df_train[_SORT_KEY] <= cutoff]

        train_end = df_train[_SORT_KEY].max() if len(df_train) else None
        gap_days = (
            float((val_start - train_end) / pd.Timedelta(days=1))
            if train_end is not None and val_start is not None else None
        )

        feature_cols = [c for c in df_sorted.columns
                        if c != target_col and not c.startswith("_")]

        X_train = df_train[feature_cols]
        X_val = df_val[feature_cols]
        y_train = df_train[target_col]
        y_val = df_val[target_col]

        def _iso(value) -> Optional[str]:
            return None if value is None or pd.isna(value) else value.isoformat()

        result = ChronologicalSplit(
            X_train=X_train,
            X_val=X_val,
            y_train=y_train,
            y_val=y_val,
            train_rows=int(len(df_train)),
            val_rows=int(len(df_val)),
            # Read off the parsed axis rather than re-parsing the raw column with
            # a bare `except Exception: return None`, which reported "no dates"
            # for a frame whose dates simply held a mixture of formats.
            train_date_min=_iso(df_train[_SORT_KEY].min() if len(df_train) else None),
            train_date_max=_iso(train_end),
            val_date_min=_iso(val_start),
            val_date_max=_iso(df_val[_SORT_KEY].max() if len(df_val) else None),
            timestamp_column=sort_col,
            rows_dropped_no_timestamp=n_unparseable,
            embargo_days=embargo,
            train_rows_before_embargo=train_rows_before,
            rows_purged_by_embargo=train_rows_before - int(len(df_train)),
            gap_days=round(gap_days, 6) if gap_days is not None else None,
            boundary_is_strict=bool(
                train_end is not None and val_start is not None
                and train_end < val_start
            ),
            # The claim worth auditing: the folds are separated by at least the
            # width asked for. False whenever an embargo was requested and the
            # data could not honour it — including when the purge emptied the
            # training fold, which leaves no measured gap at all.
            embargo_is_effective=bool(
                embargo > 0.0 and gap_days is not None and gap_days >= embargo
            ),
        )

        logger.info(
            "[DatasetSplitter] train=%d val=%d rows on '%s'; %.1fd embargo purged "
            "%d of %d, fold gap %s day(s), boundary strict=%s",
            result.train_rows, result.val_rows, sort_col, embargo,
            result.rows_purged_by_embargo, train_rows_before,
            result.gap_days, result.boundary_is_strict,
        )
        return result

    def _observation_times(self, df: pd.DataFrame):
        """(column name, parsed UTC observation times) using the shared axis.

        The shared resolver is tried first so this splitter and
        `price_model.chronological_split` order rows the same way. The fallback
        exists only for frames that predate `search_timestamp` *and* carry no
        `recorded_at` — a `recorded_date`-only extract — and it is a date, so it
        cannot order two observations from the same day.
        """
        shared = resolve_ordering_timestamp_column(df)
        if shared is not None:
            return shared, ordering_timestamps(df)
        for col in self.FALLBACK_SORT_COLS:
            if col in df.columns:
                return col, pd.to_datetime(df[col], errors="coerce", utc=True)
        raise ValueError(
            "DatasetSplitter: no time column found in DataFrame. Expected the "
            "shared observation axis (search_timestamp or recorded_at) or one of "
            f"{self.FALLBACK_SORT_COLS}."
        )


dataset_splitter = DatasetSplitter()
