"""SkyMind Forecast Engine.

Performs schema validation, loads appropriate horizon-specific predictions,
executes inference, and structures forecast timeline objects.
"""

import time
import math
import logging
from typing import Dict, Any, List, Optional
import numpy as np

from backend.services.model_registry import ModelRegistry, model_registry as default_registry
from backend.services.model_schema_validator import ModelSchemaValidator as default_validator
from backend.services.prediction_formatter import PredictionFormatter as default_formatter
from backend.services.event_publisher import EventPublisher, AuditLogEventPublisher
from backend.services.confidence_policy import (
    metrics_for_horizon,
    resolve_published_accuracy,
)
from backend.ml.price_model import get_predictor
from backend.utils.exceptions import PredictionUnavailable

logger = logging.getLogger(__name__)

class ForecastEngine:
    def __init__(
        self,
        model_registry: Optional[ModelRegistry] = None,
        model_schema_validator: Optional[Any] = None,
        predictor: Optional[Any] = None,
        formatter: Optional[Any] = None,
        event_publisher: Optional[EventPublisher] = None
    ):
        self.model_registry = model_registry or default_registry
        self.model_schema_validator = model_schema_validator or default_validator
        self.predictor = predictor or get_predictor()
        self.formatter = formatter or default_formatter
        self.event_publisher = event_publisher or AuditLogEventPublisher()

    @staticmethod
    def _resolve_published_accuracy(perf: Dict[str, Any]) -> Optional[float]:
        """Return the recorded accuracy-equivalent figure on a 0-100 scale, or None.

        Delegates to `confidence_policy` so this and `prediction_service` cannot
        drift apart; see that module for what the number is and is not. Kept as a
        method because the engine's collaborators are injected and tests address
        it here.
        """
        return resolve_published_accuracy(perf)

    def _confidence_by_horizon(self, horizons: List[int]) -> Dict[int, Optional[float]]:
        """Map each forecast horizon to the accuracy recorded for that horizon.

        Each horizon is a separately trained model with its own test fold, so its
        confidence is its own recorded metric. The previous code published one
        figure for the whole curve and decayed it in the formatter by two
        percentage points per day — an invented gradient that had nothing to do
        with how the individual models measured. The quarantined artifacts show
        why that gradient was wrong in both direction and size: the 1d model
        recorded a *higher* 100-MAPE figure than the 0d model (98.64 against
        90.59), so a monotone decay misstated the ordering it was asserting.

        A horizon with no recorded metrics maps to None, and the formatter
        publishes null rather than another horizon's number.
        """
        resolved: Dict[int, Optional[float]] = {}
        for h in horizons:
            resolved[h] = resolve_published_accuracy(
                metrics_for_horizon(self.predictor, h)
            )
        return resolved

    def run_forecast(self, snapshot_ctx: Dict[str, Any], features: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generates sequence of future forecasted rates on supported horizons."""
        # 1. Verify registry forecasting capabilities
        if not self.model_registry.supports_forecasting:
            logger.error("Registry reports active model does not support forecasting.")
            raise PredictionUnavailable("Prediction unavailable: Active model does not support forecasting.")

        # 2. Schema Validation (Assert features layout matches expected)
        #
        # Note what this does and does not cover. `features` is the vector the
        # caller built for the *point* prediction, and validating it here is worth
        # doing — but `PricePredictor.forecast` below does not consume it. It
        # rebuilds a vector per horizon from `snapshot_ctx`, so this check never saw
        # the vector the curve was computed from. That is how `forecast()` came to
        # build a `feature_set_v1` vector for a legacy-16 model with a green schema
        # validation sitting one line above the call. `forecast()` now builds to
        # `predictor.feature_set_version` and `predict()` refuses a vector carrying
        # another set's names, which is where that class of fault has to be caught.
        expected_features = self.model_registry.expected_features
        self.model_schema_validator.validate_schema(features, expected_features)

        # 3. Generate Forecast Points via PricePredictor
        forecast_start = time.time()
        forecast_raw = self.predictor.forecast(snapshot_ctx)

        # This block used to read:
        #
        #     model_acc = 95.0
        #     try:
        #         perf = getattr(self.predictor, "metrics", {}) or {}
        #         if isinstance(perf, dict) and "accuracy" in perf:
        #             model_acc = float(perf["accuracy"])
        #     except Exception:
        #         model_acc = 95.0
        #
        # After a non-legacy load, `predictor.metrics` is keyed by integer horizon
        # — {0: {...}, 1: {...}, 3: {...}} — so `"accuracy" in perf` tests a string
        # key against an int-keyed dict and is always False. Every forecast request
        # therefore published a confidence of exactly 95.0, a number with no
        # provenance. Had the branch ever been taken it would have been wrong the
        # other way, because `metrics["accuracy"]` is a 0–1 fraction being written
        # into a 0–100 field.
        #
        # Each horizon now carries the metric its own model recorded. If not one
        # horizon has a recorded metric, this refuses rather than inventing one;
        # if some do, the rest publish null.
        horizons = [int(f["day"]) for f in forecast_raw]
        confidence_by_horizon = self._confidence_by_horizon(horizons)
        if not any(v is not None for v in confidence_by_horizon.values()):
            raise PredictionUnavailable(
                "Forecast unavailable: the loaded model records no evaluation metrics "
                "for any forecast horizon, so no confidence can be published for this "
                "forecast."
            )

        # 4. Format outputs cleanly separating versions/metadata
        formatted_forecast = self.formatter.format_forecast(
            forecast_raw,
            model_version=self.model_registry.model_version,
            feature_schema_version=self.model_registry.feature_schema_version,
            confidence_by_horizon=confidence_by_horizon
        )
        
        # 5. Publish events
        self.event_publisher.publish("ForecastGenerated", {
            "origin": snapshot_ctx.get("origin"),
            "destination": snapshot_ctx.get("destination"),
            "horizons": [f["day"] for f in formatted_forecast],
            "latency_seconds": round(time.time() - forecast_start, 4)
        })
        
        return formatted_forecast
