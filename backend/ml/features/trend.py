"""Trend features over one flight's own price history.

Both branches call `backend.services.curve_window_definition.trend_features`, where
the disagreements this module used to carry are documented: ddof=1 against ddof=0
inside `trend_strength` (which `test_training_inference_parity.py` exempted from its
parity assertion rather than reconciling), a four-part curve key with no per-flight
component at all, a hardcoded `recorded_at` sort, `trend_duration` 1.0 in training
against 0.0 at inference for the same one-observation curve, and an inference
fallback that reported the quoted fare itself as `ema_7`, `ema_14`,
`rolling_median_7` and `rolling_mean_14` when there was no history.
"""

from typing import List, Dict, Any

import pandas as pd

from backend.ml.feature_generator import FeatureGenerator
from backend.ml.feature_context import FeatureContext
from backend.services.booking_curve_definition import curve_identity_from_record
from backend.services.curve_window_definition import (
    TREND_FEATURES,
    trend_features,
    trend_features_from_records,
)


class TrendGenerator(FeatureGenerator):
    @property
    def name(self) -> str:
        return "TrendGenerator"

    @property
    def feature_names(self) -> List[str]:
        return list(TREND_FEATURES)

    @property
    def category(self) -> str:
        return "trend"

    @property
    def version(self) -> str:
        # 2.0.0: shared definition, five-part curve key, no zero-filling.
        return "2.0.0"

    def transform(self, context: FeatureContext) -> Dict[str, Any]:
        if isinstance(context.historical_data, pd.DataFrame):
            return trend_features(context.historical_data)

        ctx = context.prediction_context
        # `curve_identity_from_record`, not a hand-typed dict. The callee reduces
        # this to a key by iterating `BOOKING_CURVE_KEYS`, so the literal that used
        # to sit here — naming `flight_number` — stopped supplying the per-flight
        # component when it became `departure_time` on 2026-09-03, and
        # `_curve_frame` raised `KeyError` on the first retrieved observation.
        return trend_features_from_records(
            context.historical_data,
            curve=curve_identity_from_record(ctx),
            current_price=ctx.get("current_price"),
            current_time=context.current_timestamp,
        )
