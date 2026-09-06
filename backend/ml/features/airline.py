"""Airline-level market aggregates.

Every quantity here is computed by `backend.services.market_aggregate_definition`,
called by *both* branches of `transform`. Before this rewrite the two branches were
independent implementations, and they disagreed under identical feature names in
four measurable ways:

  * the training aggregates were whole-corpus
    `groupby(route, airline).transform(...)`, so a row's `airline_average_fare`
    averaged fares quoted *after* it, including the one it was supervised against;
  * `airline_volatility` was pandas' sample std (ddof=1) in training and `np.std`
    (ddof=0) at inference;
  * `airline_route_share`'s denominator was the corpus's distinct route count in
    training and, at inference, the distinct route count of the retrieved
    history — usually 1, so the two could never agree;
  * `airline_price_rank` mapped whole-corpus means back with `pd.merge`, which
    returns a fresh `RangeIndex`. `feature_engineering_pipeline.build_training_dataset`
    assigns the result into a frame built with the *input* frame's index, and
    pandas aligns by label, so on any frame whose index is not `0..n-1` — which
    includes every training frame, because `attach_future_target` drops the rows
    it cannot label — the ranks landed on the wrong rows. A column of plausible
    small integers, silently permuted.

The aggregates are now as-of: the value for an observation recorded at time t is
computed from the observations recorded at or before t, and from nothing else.

Nothing here fills a missing value. `airline_volatility` and `airline_route_share`
used to be `.fillna(0.0)`, `airline_market_share` divided by a count
`.clip(lower=1)`, and when the airline or route columns were absent this branch
reported `airline_market_share`, `airline_route_share` and `airline_price_rank` as
1.0, `airline_volatility` as 0.0 and `airline_average_fare` as the row's own
price — a feature identical to the model's own input under a market-statistic
name. XGBoost consumes NaN natively.

The dead `airline_statistics` branch is gone; see the note in `route.py`.
"""

from typing import List, Dict, Any
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from backend.ml.feature_generator import FeatureGenerator
from backend.ml.feature_context import FeatureContext
from backend.services.market_aggregate_definition import (
    AIRLINE_FEATURES,
    airline_aggregates,
    airline_aggregates_from_records,
)


class AirlineGenerator(FeatureGenerator):
    @property
    def name(self) -> str:
        return "AirlineGenerator"

    @property
    def feature_names(self) -> List[str]:
        return ["airline_code"] + AIRLINE_FEATURES

    @property
    def category(self) -> str:
        return "airline"

    @property
    def version(self) -> str:
        # 2.0.0: as-of aggregates on a shared definition, a rank aligned by
        # index label, a corpus-wide route-share denominator, no zero-filling.
        return "2.0.0"

    def transform(self, context: FeatureContext) -> Dict[str, Any]:
        if isinstance(context.historical_data, pd.DataFrame):
            return self._transform_training(context.historical_data)
        return self._transform_inference(context)

    # ── Training: a frame of observations, one value out per row in ─────
    def _transform_training(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        if df.empty:
            return {n: pd.Series(dtype="float64") for n in self.feature_names}

        features: Dict[str, pd.Series] = {
            "airline_code": (
                df["airline_code"] if "airline_code" in df.columns
                else pd.Series(np.nan, index=df.index, dtype="float64")
            )
        }
        features.update(airline_aggregates(df))
        return features

    # ── Inference: one request, plus whatever history was retrieved ─────
    def _transform_inference(self, context: FeatureContext) -> Dict[str, Any]:
        ctx = context.prediction_context
        airline = ctx.get("airline") or ctx.get("airline_code")

        features: Dict[str, Any] = {"airline_code": airline if airline else np.nan}
        # Same function as training, on a frame ending in the fare being quoted.
        features.update(airline_aggregates_from_records(
            context.historical_data,
            query={
                "origin_code": ctx.get("origin") or ctx.get("origin_code"),
                "destination_code": ctx.get("destination") or ctx.get("destination_code"),
                "airline_code": airline,
                "departure_date": ctx.get("departure_date"),
            },
            current_price=ctx.get("current_price"),
            # A missing request time would make the quote unorderable and NaN
            # every one of the six features, silently.
            current_time=context.current_timestamp or datetime.now(timezone.utc),
        ))
        return features
