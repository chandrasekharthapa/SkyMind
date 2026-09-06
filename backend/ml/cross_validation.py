"""Time-Series Cross Validation.

Rolling-window and expanding-window validation for chronologically ordered fare
observations, with a per-fold label embargo. Never shuffles.

The version this replaces carried the claim "Future observations never leak into
any training fold" in this docstring, and shipped five things that made the claim
either false or unfalsifiable:

1. *A different time axis from the rest of the pipeline.* `SORT_COLS` was
   `["recorded_at", "recorded_date"]`, so this validator ordered folds by insert
   time while `price_model.chronological_split` ordered by the search instant —
   when the fare was actually observed. Two orderings of one corpus cut different
   folds, so the cross-validated metric and the holdout metric were not
   measurements of the same experiment even though the training report printed
   them side by side. Both paths now resolve the axis through
   `booking_curve_definition.ordering_timestamps`, which coalesces per row.

2. *Sorting the raw column.* `df.sort_values("recorded_at")` on a column of ISO
   strings is a lexicographic sort. It agrees with chronology only while every
   value shares a format and a UTC offset, and `price_history` holds both
   tz-aware values from Supabase and naive ones from CSV loads. Rows whose
   timestamp did not parse at all sorted to the end, which is the last fold's
   validation slice. They are now dropped, and counted in the report.

3. *No embargo.* Ordering by observation time puts each fold's training features
   before its validation slice and says nothing about the training rows' *labels*,
   which are fares observed later on the same booking curve: the label for a row
   observed at `t` is a fare at or after `t + h`. One boundary is one leak; here
   there are `n_folds` boundaries, which is why cross-validated error could come
   out *below* holdout error and read as good news.

4. *A rolling window narrower than one fold.* `train_end = train_start +
   fold_size * (n_folds - 1) // n_folds` made each rolling training window a
   fraction of a single fold — 50 rows where `fold_size` was 75 — and exactly
   zero rows at `n_folds=1`, so rolling validation with one fold silently
   produced no folds at all and reported all-NaN metrics. The line above it,
   `window = fold_size * n_folds // n_folds  # rolling window = fold_size`,
   computed the intended width, was never read, and is now the implementation.

5. *A report with no timestamps in it.* `CrossValidationReport` carried metrics
   and row counts only, so nothing it published could confirm or refute the claim
   at the top of this file. Each fold now records the span it was observed over,
   its gap to its own validation slice, and whether the embargo it was given was
   achieved — and a fold that was skipped records why, instead of vanishing and
   leaving an unexplained all-NaN average behind.

Zero Synthetic Feature Policy: no fabricated rows are added.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Iterator, Tuple

import numpy as np
import pandas as pd

from backend.ml import metrics as m
from backend.services.booking_curve_definition import (
    FALLBACK_TIMESTAMP_KEY,
    ORDERING_TIMESTAMP_KEY,
    ordering_timestamps,
    resolve_ordering_timestamp_column,
)

logger = logging.getLogger(__name__)

# The parsed observation time, added for the sort and never offered as a feature:
# `validate` only ever selects from the caller's `feature_cols`.
_SORT_KEY = "_cv_observed_at"


def _iso(value: Any) -> Optional[str]:
    """ISO-8601 for a Timestamp, None for anything missing."""
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


@dataclass
class CrossValidationReport:
    """Complete cross-validation result for one model/horizon."""

    strategy: str                        # "expanding" or "rolling"
    n_folds: int                         # folds actually scored, not folds attempted
    fold_metrics: List[Dict[str, float]] # one dict per scored fold
    avg_metrics: Dict[str, float]        # mean across scored folds
    std_metrics: Dict[str, float]        # std across scored folds
    feature_set_version: str
    forecast_horizon: int
    # Appended with defaults so the seven fields above stay positionally
    # constructible. `fold_windows` is a separate list rather than extra keys on
    # `fold_metrics` because that one is typed `Dict[str, float]` and is spliced
    # into `EvaluationReport.fold_metrics`, which declares the same type: ISO
    # timestamps in those dicts would make the annotation wrong in two files.
    timestamp_column: Optional[str] = None
    rows_dropped_no_timestamp: int = 0
    embargo_days: float = 0.0
    fold_windows: List[Dict[str, Any]] = field(default_factory=list)
    boundary_is_strict_in_every_fold: bool = False
    embargo_is_effective_in_every_fold: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "n_folds": self.n_folds,
            "fold_metrics": self.fold_metrics,
            "avg_metrics": self.avg_metrics,
            "std_metrics": self.std_metrics,
            "feature_set_version": self.feature_set_version,
            "forecast_horizon": self.forecast_horizon,
            "timestamp_column": self.timestamp_column,
            "rows_dropped_no_timestamp": self.rows_dropped_no_timestamp,
            "embargo_days": self.embargo_days,
            "fold_windows": self.fold_windows,
            "boundary_is_strict_in_every_fold": self.boundary_is_strict_in_every_fold,
            "embargo_is_effective_in_every_fold": self.embargo_is_effective_in_every_fold,
        }


class TimeSeriesCrossValidator:
    """Rolling-window and expanding-window cross-validator.

    Neither strategy ever shuffles data. Each fold's training rows were observed
    before that fold's validation rows, and with `embargo_days > 0` no surviving
    training row's label could have been realised on or after the first
    validation observation of its own fold.
    """

    # Only consulted when the shared axis resolves to nothing. `recorded_date` is
    # a date, not an instant, so it cannot order two observations made on the same
    # day — which is why it is a last resort and not a peer of the shared keys.
    FALLBACK_SORT_COLS = ["recorded_date"]
    STRATEGIES = ("expanding", "rolling")

    def _check_strategy(self, strategy: str) -> str:
        """Raise on an unknown strategy, from one place so the message can't drift."""
        if strategy not in self.STRATEGIES:
            raise ValueError(
                f"Unknown validation_strategy: {strategy!r}. "
                f"Use one of {list(self.STRATEGIES)}."
            )
        return strategy

    def _observation_times(self, df: pd.DataFrame) -> Tuple[str, pd.Series]:
        """(column name, parsed UTC observation times) using the shared axis.

        The shared resolver comes first so this validator, `DatasetSplitter` and
        `price_model.chronological_split` all order rows the same way. The
        fallback covers frames that predate `search_timestamp` *and* carry no
        `recorded_at`.
        """
        shared = resolve_ordering_timestamp_column(df)
        if shared is not None:
            return shared, ordering_timestamps(df)
        for col in self.FALLBACK_SORT_COLS:
            if col in df.columns:
                return col, pd.to_datetime(df[col], errors="coerce", utc=True)
        raise ValueError(
            "No time column found. Expected the shared observation axis "
            f"('{ORDERING_TIMESTAMP_KEY}' or '{FALLBACK_TIMESTAMP_KEY}') or one "
            f"of {self.FALLBACK_SORT_COLS}."
        )

    def _iter_folds(
        self,
        df_sorted: pd.DataFrame,
        n_folds: int,
        strategy: str,
    ) -> Iterator[Tuple[pd.DataFrame, pd.DataFrame]]:
        """Yield (df_train, df_val) per fold, training always earlier than validation.

        `min_train_rows` is deliberately no longer a parameter here. The old
        signature took it and `continue`d on any fold it judged too small, which
        is how a run could report zero folds and all-NaN averages with nothing
        recording which folds had existed or why each was dropped. Sizing
        verdicts now belong to `validate`, which writes one down per fold.
        """
        self._check_strategy(strategy)
        n = len(df_sorted)
        # One fold's worth of rows, sized so that `n_folds` validation slices and
        # the first training window all fit: (n_folds + 1) * fold_size <= n.
        fold_size = max(1, n // (n_folds + 1))

        if strategy == "expanding":
            for i in range(1, n_folds + 1):
                train_end = fold_size * i
                val_end = min(train_end + fold_size, n)
                if train_end <= 0 or val_end <= train_end:
                    continue
                yield df_sorted.iloc[:train_end], df_sorted.iloc[train_end:val_end]
            return

        # Rolling: a window exactly one fold wide that advances one fold per step.
        # That width is what the deleted `window = fold_size * n_folds // n_folds`
        # line computed and never used, while the expression actually in force
        # took `fold_size * (n_folds - 1) // n_folds` — narrower than one fold at
        # every `n_folds`, and zero rows wide at `n_folds=1`.
        for i in range(n_folds):
            train_start = i * fold_size
            train_end = train_start + fold_size
            val_end = min(train_end + fold_size, n)
            if val_end <= train_end:
                continue
            yield (df_sorted.iloc[train_start:train_end],
                   df_sorted.iloc[train_end:val_end])

    def validate(
        self,
        df: pd.DataFrame,
        model,                          # XGBRegressor (already instantiated, not fitted)
        feature_cols: List[str],
        target_col: str,
        n_folds: int,
        strategy: str,
        feature_set_version: str,
        forecast_horizon: int,
        min_train_rows: int = 20,
        random_seed: int = 42,
        embargo_days: float = 0.0,
    ) -> CrossValidationReport:
        """Run cross-validation and return CrossValidationReport.

        Args:
            df: Feature-engineered DataFrame (must contain target_col + a time column).
            model: Unfitted XGBRegressor instance (cloned per fold).
            feature_cols: Columns to use as features.
            target_col: Name of the regression target column.
            n_folds: Number of CV folds to attempt.
            strategy: "expanding" or "rolling".
            feature_set_version: Feature set identifier for the report.
            forecast_horizon: Horizon in days.
            min_train_rows: Minimum training rows required to score a fold.
            random_seed: Passed to each fold model.
            embargo_days: Width of the label embargo, applied at every fold
                boundary. Training rows observed within this many days of that
                fold's first validation observation are dropped, because their
                labels are fares recorded inside that fold's validation window.
                Pass `h + lag_tolerance_days(h)` for a model at horizon `h`; 0.0
                reproduces the old behaviour and is not safe for a
                forward-looking label.

        Returns:
            CrossValidationReport
        """
        self._check_strategy(strategy)
        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found in DataFrame.")

        sort_col, observed = self._observation_times(df)
        frame = df.copy()
        frame[_SORT_KEY] = observed
        n_unparseable = int(frame[_SORT_KEY].isna().sum())
        if n_unparseable:
            # Dropped rather than left to sort to one end. NaT sorts last, so
            # these used to land in the final fold's validation slice — the slice
            # whose whole meaning is "later than its training rows", filled with
            # rows whose time is unknown.
            logger.warning(
                "[CV] %d of %d row(s) have no parseable observation time in '%s' "
                "and are excluded from every fold.",
                n_unparseable, len(frame), sort_col,
            )
            frame = frame[frame[_SORT_KEY].notna()]
        if frame.empty:
            raise ValueError(
                f"[CV] no row in the {len(df)}-row frame has a parseable "
                f"observation time in '{sort_col}'."
            )

        # `mergesort` is stable, so rows sharing a timestamp keep their input
        # order and the folds are reproducible for a given frame.
        df_sorted = frame.sort_values(_SORT_KEY, kind="mergesort").reset_index(drop=True)

        embargo = max(0.0, float(embargo_days))
        fold_metrics: List[Dict[str, float]] = []
        fold_windows: List[Dict[str, Any]] = []

        for fold_idx, (df_train, df_val) in enumerate(
            self._iter_folds(df_sorted, n_folds, strategy)
        ):
            # Appended before any verdict is reached, so a fold that is skipped
            # still appears in the report with the reason attached.
            window: Dict[str, Any] = {"fold": fold_idx + 1, "scored": False,
                                      "skip_reason": None}
            fold_windows.append(window)

            valid_feature_cols = [c for c in feature_cols
                                  if c in df_train.columns and c in df_val.columns]

            # Rows without a target are dropped from the frames rather than
            # masked out of X and y, so `_SORT_KEY` stays aligned with the rows
            # the fit actually consumes. Masking X/y separately left the window
            # this fold reports describing a different row set from the one it
            # was scored on.
            df_train = df_train[df_train[target_col].notna()]
            df_val = df_val[df_val[target_col].notna()]

            # The purge, on this fold's training slice only: dropping validation
            # rows would discard the measurement rather than the contamination.
            rows_before = int(len(df_train))
            val_start = df_val[_SORT_KEY].min() if len(df_val) else None
            cutoff = None
            if embargo > 0.0 and rows_before and val_start is not None:
                cutoff = val_start - pd.Timedelta(days=embargo)
                df_train = df_train[df_train[_SORT_KEY] <= cutoff]

            train_start = df_train[_SORT_KEY].min() if len(df_train) else None
            train_end = df_train[_SORT_KEY].max() if len(df_train) else None
            gap_days = (
                float((val_start - train_end) / pd.Timedelta(days=1))
                if train_end is not None and val_start is not None else None
            )
            purged = rows_before - int(len(df_train))
            window.update({
                "train_rows_before_embargo": rows_before,
                "rows_purged_by_embargo": purged,
                "train_rows": int(len(df_train)),
                "val_rows": int(len(df_val)),
                "train_start": _iso(train_start),
                "train_end": _iso(train_end),
                "val_start": _iso(val_start),
                "val_end": _iso(df_val[_SORT_KEY].max() if len(df_val) else None),
                "embargo_cutoff": _iso(cutoff),
                "gap_days": round(gap_days, 6) if gap_days is not None else None,
                "boundary_is_strict": bool(
                    train_end is not None and val_start is not None
                    and train_end < val_start
                ),
                # The auditable claim: this fold's folds are separated by at
                # least the width asked for. False whenever an embargo was
                # requested and the fold could not honour it.
                "embargo_is_effective": bool(
                    embargo > 0.0 and gap_days is not None and gap_days >= embargo
                ),
            })

            if not valid_feature_cols:
                window["skip_reason"] = (
                    "none of the %d requested feature column(s) is present in "
                    "both folds" % len(feature_cols)
                )
                continue
            if not len(df_val):
                window["skip_reason"] = "no validation row in this fold has a target"
                continue
            if len(df_train) < min_train_rows:
                window["skip_reason"] = (
                    "%d training row(s), below min_train_rows=%d%s"
                    % (len(df_train), min_train_rows,
                       (" — a %.1fd embargo purged %d of %d"
                        % (embargo, purged, rows_before)) if purged else "")
                )
                continue

            # Clone and train
            from sklearn.base import clone
            fold_model = clone(model)
            fold_model.random_state = random_seed
            fold_model.fit(df_train[valid_feature_cols], df_train[target_col])

            preds = fold_model.predict(df_val[valid_feature_cols])
            fold_m = m.compute_all(df_val[target_col].values, preds)
            fold_m["fold"] = float(fold_idx + 1)
            fold_m["train_rows"] = float(len(df_train))
            fold_m["val_rows"] = float(len(df_val))
            fold_m["rows_purged_by_embargo"] = float(purged)
            fold_metrics.append(fold_m)
            window["scored"] = True

            logger.info(
                "[CV] Fold %d/%d  train=%d (purged %d) val=%d  gap=%s d  "
                "MAE=%.2f  R²=%.4f",
                fold_idx + 1, n_folds, len(df_train), purged, len(df_val),
                window["gap_days"], fold_m["mae"], fold_m["r2"],
            )

        # Aggregate
        metric_keys = m.METRIC_KEYS   # the set `compute_all` above returns, not a re-listing of it
        avg_metrics: Dict[str, float] = {}
        std_metrics: Dict[str, float] = {}

        if fold_metrics:
            for k in metric_keys:
                vals = [f[k] for f in fold_metrics if k in f and not np.isnan(f[k])]
                avg_metrics[k] = float(np.mean(vals)) if vals else float("nan")
                std_metrics[k] = float(np.std(vals)) if len(vals) > 1 else 0.0
        else:
            for k in metric_keys:
                avg_metrics[k] = float("nan")
                std_metrics[k] = float("nan")

        scored = [w for w in fold_windows if w["scored"]]
        for window in fold_windows:
            if window["skip_reason"]:
                logger.warning("[CV] Fold %d not scored: %s",
                               window["fold"], window["skip_reason"])

        report = CrossValidationReport(
            strategy=strategy,
            n_folds=len(fold_metrics),
            fold_metrics=fold_metrics,
            avg_metrics=avg_metrics,
            std_metrics=std_metrics,
            feature_set_version=feature_set_version,
            forecast_horizon=forecast_horizon,
            timestamp_column=sort_col,
            rows_dropped_no_timestamp=n_unparseable,
            embargo_days=embargo,
            fold_windows=fold_windows,
            # `bool(scored) and all(...)`, not `all(...)` alone: `all([])` is True,
            # and a report asserting every fold was clean when no fold ran is the
            # same vacuous pass as `if not np.isnan(avg_mae): assert avg_mae >= 0`.
            boundary_is_strict_in_every_fold=bool(scored) and all(
                w["boundary_is_strict"] for w in scored),
            embargo_is_effective_in_every_fold=bool(scored) and embargo > 0.0 and all(
                w["embargo_is_effective"] for w in scored),
        )

        logger.info(
            "[CV] Done — %d of %d fold(s) scored on '%s'; %.1fd embargo, "
            "avg MAE=%.2f  avg R²=%.4f  strict in every fold=%s",
            report.n_folds, len(fold_windows), sort_col, embargo,
            avg_metrics.get("mae", float("nan")),
            avg_metrics.get("r2", float("nan")),
            report.boundary_is_strict_in_every_fold,
        )
        return report


time_series_cross_validator = TimeSeriesCrossValidator()
