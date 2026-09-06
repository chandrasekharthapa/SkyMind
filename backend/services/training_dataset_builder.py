"""Training Dataset Builder.

Loads raw historical flight observations, removes duplicates, validates
chronology, and attaches the supervised label for a given horizon.

The label is `booking_curve_definition.attach_future_target`, shared with
`PriceModel._build_shifted_dataset` so that the frame the model trains on and the
frame the target-leakage tests inspect are produced by the same code. Before the
2026-08 fix pass this method built the label itself, and the two differed:

  * horizon 0 assigned `df_features["target_price"] = df_features["price"]` — the
    label was the feature row's own price, so every price-derived feature was a
    function of the target and the reported r² measured the join, not skill;
  * the join for horizon > 0 appended `flight_number` to its keys only inside
    `if "flight_number" in target_df.columns`, and `target_df` was built by a
    column selection that never included it, so the condition was always False
    and the label was another flight's later fare;
  * it matched on calendar-date equality and kept the first row of the target
    day, while `_build_shifted_dataset` took that day's minimum, and only the
    latter had tests.
"""

import logging
from typing import Tuple
import pandas as pd
from backend.database.database import database as db

logger = logging.getLogger(__name__)

class TrainingDatasetBuilder:
    def __init__(self):
        pass

    def build(self, horizon: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Loads raw records and constructs the supervised training dataset for a horizon.

        Raises ValueError for a horizon below `MIN_TRAINABLE_HORIZON_DAYS`; see
        `attach_future_target` for why that is not a dataset that can be built.
        """
        from backend.services.booking_curve_definition import (
            BOOKING_CURVE_KEYS,
            FALLBACK_TIMESTAMP_KEY,
            MIN_TRAINABLE_HORIZON_DAYS,
            ORDERING_TIMESTAMP_KEY,
            attach_future_target,
            deduplicate_session_aware,
            ordering_timestamps,
            resolve_ordering_timestamp_column,
            sort_booking_curves_chronologically,
        )

        # Refuse before touching the database: an unbuildable horizon should not
        # cost a 100k-row query, and the caller needs the same error whether or
        # not there happens to be data today.
        if int(horizon) < MIN_TRAINABLE_HORIZON_DAYS:
            raise ValueError(
                f"[TrainingDatasetBuilder] horizon {horizon} is not trainable "
                f"(minimum {MIN_TRAINABLE_HORIZON_DAYS}d): the label would be the "
                f"observation's own price."
            )

        df_raw = db.get_training_dataset()
        from backend.services.training_eligibility import filter_training_eligible_dataframe
        df_raw = filter_training_eligible_dataframe(df_raw)

        if df_raw.empty:
            # An empty frame has two causes and they are not equivalent: no
            # eligible observations, or a loader that failed. `get_training_dataset`
            # records which in `last_load_failed`; reporting them the same way is
            # how a broken database connection came to look like a quiet dataset.
            if getattr(db, "last_load_failed", False):
                logger.error(
                    "[TrainingDatasetBuilder] Training data load FAILED — the "
                    "empty frame is a loader error, not an empty dataset."
                )
            else:
                logger.warning("[TrainingDatasetBuilder] No eligible training observations found.")
            return pd.DataFrame(), pd.DataFrame()

        # 1. Session-aware duplicate removal
        df_raw = deduplicate_session_aware(df_raw)

        # 2. Chronological ordering & booking curve construction
        df_raw = sort_booking_curves_chronologically(df_raw)

        # Chronology validation: departure_date must be >= observation date.
        # The observation column comes from the shared resolver, so this filter
        # and the label join below cannot disagree about which timestamp means
        # "when this fare was seen" — they did, and the target join was aligned
        # on the column the ordering did not use.
        ts_col = resolve_ordering_timestamp_column(df_raw)
        if ts_col is None:
            raise ValueError(
                "[TrainingDatasetBuilder] no observation timestamp column "
                "(search_timestamp or recorded_at) on the training frame; "
                "without one, chronology cannot be checked and the label cannot "
                "be dated."
            )
        # `pd.to_datetime(df_raw[ts_col])` — reading the single resolved column —
        # is what this was. `resolve_ordering_timestamp_column` returns
        # `search_timestamp` whenever the column exists, so a row holding NULL
        # there got `recorded_datetime` NaT and `recorded_date` None, and the
        # chronology filter below — `departure_date_dt >= recorded_date` —
        # compared its date against None, evaluated False, and dropped it. With
        # the column NULL across a frame the builder dropped all of it and logged
        # "every observation was recorded after its departure date", which is not
        # what happened and sent the reader looking at the corpus instead of at
        # this line. `ordering_timestamps` coalesces per row, so `recorded_at`
        # covers any row the writer left without a search timestamp. (This comment
        # used to assert the all-NULL frame as the live state of `price_history`.
        # Measured 2026-09-03 on a 35,894-row export: `search_timestamp` is
        # populated on every row, so the failure was reachable, not occurring.)
        df_raw["recorded_datetime"] = ordering_timestamps(df_raw)
        df_raw["recorded_date"] = df_raw["recorded_datetime"].dt.date
        # `format="ISO8601", utc=True` for the reason recorded in
        # `booking_curve_definition.booking_horizon_days`. A NaT here is dropped by
        # the chronology filter below, so an unparsed departure date silently
        # shrinks the training set.
        df_raw["departure_date_dt"] = pd.to_datetime(
            df_raw["departure_date"], errors="coerce", utc=True,
            format="ISO8601").dt.date

        # Undated rows are dropped explicitly and counted, rather than falling out
        # of the comparison below as though they departed before they were seen.
        undated = int(df_raw["recorded_datetime"].isna().sum())
        if undated:
            logger.warning(
                "[TrainingDatasetBuilder] %d of %d observation(s) carry no usable "
                "observation time in either %s or %s; they cannot be placed on a "
                "booking curve and are excluded.",
                undated, len(df_raw), ORDERING_TIMESTAMP_KEY, FALLBACK_TIMESTAMP_KEY,
            )
            df_raw = df_raw[df_raw["recorded_datetime"].notna()]
            if df_raw.empty:
                logger.error(
                    "[TrainingDatasetBuilder] no observation in the corpus carries "
                    "a usable observation time. This is a corpus defect, not an "
                    "absence of data: the rows exist and carry fares."
                )
                return df_raw, pd.DataFrame()

        # Filter out records where booking happens after departure
        undeparted = df_raw["departure_date_dt"] >= df_raw["recorded_date"]
        df_raw = df_raw[undeparted]
        if df_raw.empty:
            logger.warning(
                "[TrainingDatasetBuilder] every observation was recorded after its "
                "departure date; nothing left to train on."
            )
            return df_raw, pd.DataFrame()

        # 3. Engineer features on the raw dataset FIRST (ensures training/inference parity)
        # Both imports stay inside the function. `model_registry` imports
        # `price_model`, whose `train()` is what calls this builder, so a
        # module-level import here puts a cycle between the two files one refactor
        # away from closing.
        from backend.services.model_registry import model_registry
        from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline

        # `model_registry.feature_set_version` is type-guarded to return one of the
        # two names `feature_engineering_pipeline` knows. This used to be followed by
        # `from unittest.mock import MagicMock` and an isinstance check that
        # recomputed the same fallback the registry computes — production code
        # importing a test library to undo a value the registry should not have
        # handed out. The guard lives in the registry now, where the `-> str` is
        # promised.
        fs_version = model_registry.feature_set_version

        logger.info(f"[TrainingDatasetBuilder] Engineering features on raw data using version '{fs_version}'...")
        df_features_raw = feature_engineering_pipeline.build_training_dataset(df_raw, fs_version)

        # 4. Attach the label. `attach_future_target` works on the raw frame,
        #    which carries the full booking-curve key and the observation
        #    timestamps, and drops rows with no observation `horizon` days later.
        #    Its result keeps df_raw's index labels, which is what makes the
        #    column attachment below safe: the previous implementation assigned
        #    `df_features[col] = df_raw[col]` onto a frame that `pd.merge` had
        #    given a fresh RangeIndex, so `training_weight` — consumed as XGBoost
        #    sample weights in `model_trainer.py` — was aligned to whichever row
        #    happened to share a label, and NaN elsewhere.
        df_labelled = attach_future_target(df_raw, int(horizon))
        df_features = df_features_raw.loc[df_labelled.index].copy()
        df_features["target_price"] = df_labelled["target_price"]

        # Identity columns the split, the group-awareness and the metadata need.
        # Selected by name from the raw frame and aligned by label.
        #
        # The curve identity comes from `BOOKING_CURVE_KEYS` rather than being
        # re-typed here. It was re-typed, and it named `flight_number`; when the
        # per-flight component became `departure_time` this list would have carried
        # a column nothing groups on and omitted the one the group-aware split
        # keys by, so `group_overlap` would have been computed over four columns
        # while claiming five — a purge/embargo check that quietly stops seeing the
        # sibling departures it exists to separate.
        carry = list(BOOKING_CURVE_KEYS) + [
            "departure_date_dt", "recorded_date", "recorded_at",
            "search_timestamp", "price", "training_weight",
        ]
        for col in carry:
            if col in df_raw.columns:
                df_features[col] = df_raw[col].reindex(df_features.index)

        logger.info(
            f"[TrainingDatasetBuilder] Label attached at horizon {horizon}d. "
            f"Raw observations: {len(df_raw)}, labelled rows: {len(df_features)} "
            f"({len(df_raw) - len(df_features)} had no observation {horizon}d later)."
        )

        return df_raw, df_features

training_dataset_builder = TrainingDatasetBuilder()

