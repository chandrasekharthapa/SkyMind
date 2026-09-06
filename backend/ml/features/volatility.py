"""Volatility features over one flight's own price history.

Both branches call `backend.services.curve_window_definition.volatility_features`,
which is where the defects this module used to carry are documented: pandas ddof=1
in training against `np.std` ddof=0 at inference under one feature name, a
four-part curve key that pooled two flights of one airline, a hardcoded
`recorded_at` sort where the pipeline orders on `search_timestamp`, and
`.fillna(0.0)` / `.clip(lower=1.0)` on every quantity that could be unknown.
"""

from typing import List, Dict, Any

import pandas as pd

from backend.ml.feature_generator import FeatureGenerator
from backend.ml.feature_context import FeatureContext
from backend.services.booking_curve_definition import curve_identity_from_record
from backend.services.curve_window_definition import (
    VOLATILITY_FEATURES,
    volatility_features,
    volatility_features_from_records,
)


class VolatilityGenerator(FeatureGenerator):
    @property
    def name(self) -> str:
        return "VolatilityGenerator"

    @property
    def feature_names(self) -> List[str]:
        return list(VOLATILITY_FEATURES)

    @property
    def category(self) -> str:
        return "volatility"

    @property
    def version(self) -> str:
        # 2.0.0: shared definition, five-part curve key, no zero-filling.
        return "2.0.0"

    def transform(self, context: FeatureContext) -> Dict[str, Any]:
        if isinstance(context.historical_data, pd.DataFrame):
            return volatility_features(context.historical_data)

        ctx = context.prediction_context
        # `curve_identity_from_record`, not a hand-typed dict — same defect and same
        # fix as `trend.py`. Both generators hand this straight to `_curve_frame`,
        # which compares it against a retrieved row for every key in
        # `BOOKING_CURVE_KEYS`.
        return volatility_features_from_records(
            context.historical_data,
            curve=curve_identity_from_record(ctx),
            current_price=ctx.get("current_price"),
            current_time=context.current_timestamp,
        )
