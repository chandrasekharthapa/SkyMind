"""Route-level market aggregates.

Every quantity here is computed by `backend.services.market_aggregate_definition`,
called by *both* branches of `transform`. Before this rewrite the two branches were
independent implementations that disagreed under identical feature names —
`historical_price_std` was pandas' sample std (ddof=1) in training and `np.std`
(ddof=0) at inference, and the training aggregates were whole-corpus
`groupby(route).transform(...)`, so a row's `historical_maximum_fare` was the
maximum over observations recorded *after* it, including the one it was supervised
against. On a 75-row batch-written fixture, 3 rows had a whole-corpus route max
exactly equal to their own fare.

The aggregates are now as-of: the value for an observation recorded at time t is
computed from the observations recorded at or before t, and from nothing else.
That is the property `booking_curve_validator.validate_target_leakage` tests by
masking the frame at t and recomputing, which is why it can now prove this rather
than assume it.

Nothing here fills a missing value. `historical_price_std` used to be
`.fillna(0.0)` — "this route showed no variation" for a route with one
observation — and when the airline or lead-time columns were absent this reported
`airline_count` as 1.0 and `average_booking_lead` as 0.0. XGBoost consumes NaN
natively.

The dead `route_statistics` branch is gone. Every production call site passes
`route_statistics={}` (`feature_engineering_pipeline.py`, `prediction_service.py`,
`price_model.py`), so the branch never ran; had it ever run it would have injected
precomputed whole-corpus statistics, which is the defect this module exists to
remove.
"""

from typing import List, Dict, Any
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from backend.ml.feature_generator import FeatureGenerator
from backend.ml.feature_context import FeatureContext
from backend.services.market_aggregate_definition import (
    ROUTE_FEATURES,
    route_aggregates,
    route_aggregates_from_records,
)


class RouteGenerator(FeatureGenerator):
    @property
    def name(self) -> str:
        return "RouteGenerator"

    @property
    def feature_names(self) -> List[str]:
        return ["origin_code", "destination_code"] + ROUTE_FEATURES

    @property
    def category(self) -> str:
        return "route"

    @property
    def version(self) -> str:
        # 2.0.0: as-of aggregates on a shared definition, no zero-filling.
        return "2.0.0"

    def transform(self, context: FeatureContext) -> Dict[str, Any]:
        if isinstance(context.historical_data, pd.DataFrame):
            return self._transform_training(context.historical_data)
        return self._transform_inference(context)

    # ── Training: a frame of observations, one value out per row in ─────
    def _transform_training(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        if df.empty:
            return {n: pd.Series(dtype="float64") for n in self.feature_names}

        features: Dict[str, pd.Series] = {}
        for col in ("origin_code", "destination_code"):
            features[col] = (
                df[col] if col in df.columns
                else pd.Series(np.nan, index=df.index, dtype="float64")
            )
        features.update(route_aggregates(df))
        return features

    # ── Inference: one request, plus whatever history was retrieved ─────
    def _transform_inference(self, context: FeatureContext) -> Dict[str, Any]:
        ctx = context.prediction_context
        origin = ctx.get("origin") or ctx.get("origin_code")
        destination = ctx.get("destination") or ctx.get("destination_code")

        features: Dict[str, Any] = {
            "origin_code": origin if origin else np.nan,
            "destination_code": destination if destination else np.nan,
        }
        # Same function as training, on a frame ending in the fare being quoted.
        features.update(route_aggregates_from_records(
            context.historical_data,
            query={
                "origin_code": origin,
                "destination_code": destination,
                "airline_code": ctx.get("airline") or ctx.get("airline_code"),
                "departure_date": ctx.get("departure_date"),
            },
            current_price=ctx.get("current_price"),
            # A missing request time would make the quote unorderable and NaN
            # every one of the eight features, silently.
            current_time=context.current_timestamp or datetime.now(timezone.utc),
        ))
        return features
