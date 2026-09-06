"""Snapshot-level market features: one route, one search.

Both branches of `transform` route every statistic through
`backend.services.market_aggregate_definition`, which is also what
`MarketSnapshotProvider` calls to compute the numbers it stores on a live
`MarketSnapshot`. Before this rewrite the two branches were independent
implementations that disagreed under identical feature names:

  * `price_std_dev` was `gp["price"].transform("std").fillna(0.0)` in training —
    pandas' sample std, ddof=1, with an unknown reported as 0.0 — against
    `float(np.std(prices)) if len(prices) > 1 else 0.0` at serve time, the
    population std, ddof=0. Now ddof=1 on both sides, NaN below
    `MIN_OBSERVATIONS_FOR_STD` observations.

  * `total_live_flights` counted non-null fares in training (`transform("count")`)
    and every flight returned at serve time (`len(flights)`). Now the group's
    size on both sides, with the fare-bearing share reported separately as
    `snapshot_completeness`.

  * `direct_ratio` divided by the *price* count in training and by the snapshot
    size at serve time, and both resolved an unknown stop count to "direct" — the
    provider because `stops` defaults to 0 before the itinerary check, this module
    because a missing `stops` column reported `direct_ratio` 1.0 and
    `connecting_ratio` 0.0. Now both divide by the flights whose stop count is
    known, and report NaN when none is.

  * `snapshot_quality` and `snapshot_completeness` were the literals 1.0 and 1.0
    for every training row while the provider computed them, so the model was
    trained to treat them as constants and then shown 0.72 in production. Both are
    now computed from the group by `snapshot_quality_score`.

The grouping changed too, and that was the leak. It was
`(origin_code, destination_code, recorded_at)` while the pipeline orders
observations by `search_timestamp`. Where those two agree the group is one search
and nothing leaks — measured, this is why `feature_set_v1` passed the leakage
check. Where they do not, which is exactly what a nightly batch write produces
when it stamps one `recorded_at` on rows searched hours apart, the group spans
searches and every statistic reads fares quoted after the row: on a batch-written
fixture, eight of the twelve features moved once the corpus was
masked, `lowest_fare` from 4588 to 6727 and `total_live_flights` from 2 to 1.
The group is now keyed on the resolved ordering column, which makes it
mask-invariant by construction rather than by coincidence.

The `len(group_cols) >= 2` fallback is gone. It fired whenever fewer than two of
the three key columns were present and reported `lowest_fare`, `highest_fare`,
`average_fare` and `median_fare` as the row's own price, `price_std_dev` as 0.0,
`total_live_flights` as 1, `direct_ratio` as 1.0 and `airline_diversity` as 1 —
four market statistics identical to the model's own input column, under names
that claim to describe the market around it. A frame with no route identity now
raises.

`demand_score` and `seasonality_factor` are NaN in both branches and are computed
nowhere in the repository. They are kept in `feature_names` because the shipped
feature-set contract lists them, and left NaN rather than filled, so that an
unimplemented feature reads as missing instead of as a number.
"""

from typing import List, Dict, Any

import numpy as np
import pandas as pd

from backend.ml.feature_generator import FeatureGenerator
from backend.ml.feature_context import FeatureContext
from backend.services.market_aggregate_definition import (
    SNAPSHOT_FEATURES,
    snapshot_aggregates,
    snapshot_aggregates_from_snapshot,
)

# Declared by the feature-set contract, computed nowhere. Not filled.
UNIMPLEMENTED_FEATURES: List[str] = ["demand_score", "seasonality_factor"]


class MarketGenerator(FeatureGenerator):
    @property
    def name(self) -> str:
        return "MarketGenerator"

    @property
    def feature_names(self) -> List[str]:
        return UNIMPLEMENTED_FEATURES + ["is_live"] + SNAPSHOT_FEATURES

    @property
    def category(self) -> str:
        return "market"

    @property
    def version(self) -> str:
        # 2.0.0: snapshot keyed on the ordering column, shared definition, no fills.
        return "2.0.0"

    def transform(self, context: FeatureContext) -> Dict[str, Any]:
        if isinstance(context.historical_data, pd.DataFrame):
            return self._transform_training(context.historical_data)
        return self._transform_inference(context)

    def _transform_training(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        if df.empty:
            return {name: pd.Series(dtype="float64") for name in self.feature_names}

        features: Dict[str, pd.Series] = {
            name: pd.Series(np.nan, index=df.index, dtype="float64")
            for name in UNIMPLEMENTED_FEATURES
        }
        # Passed through, not asserted. This used to be the literal False in
        # training against the literal True at inference: a feature guaranteed to
        # disagree between the two paths for every row of every dataset.
        features["is_live"] = (
            df["is_live"] if "is_live" in df.columns
            else pd.Series(np.nan, index=df.index, dtype="float64")
        )
        features.update(snapshot_aggregates(df))
        return features

    def _transform_inference(self, context: FeatureContext) -> Dict[str, Any]:
        features: Dict[str, Any] = {name: np.nan for name in UNIMPLEMENTED_FEATURES}
        features["is_live"] = True
        features.update(snapshot_aggregates_from_snapshot(context.market_snapshot))
        return features
