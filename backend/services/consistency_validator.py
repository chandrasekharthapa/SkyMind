"""Prediction Consistency Validator.

Observational plausibility checks on a single prediction, at the moment it is
made: is the predicted fare inside a sane multiple of the fares actually on offer,
and does day 1 of the forecast agree with the point prediction. It records
telemetry and never alters an inference value.

What this validator cannot do, and used to claim: **forecast error**. MAE, RMSE,
MAPE, bias and drift were initialised to `0.0` here, never assigned again, logged
once per forecast day as "Observational Metrics for Horizon Nd — MAE: 0.00,
RMSE: 0.00 …" and returned in a `metrics` block that `prediction_service`
published in every `ForecastValidated` event. A perfect-accuracy reading, emitted
for every prediction, computed from nothing.

The reason it cannot compute them is structural, not a missing implementation:
error needs the fare that was *realised* after the forecast horizon elapsed, and
nothing at prediction time knows it. That measurement belongs to, and now lives
only in, `forecast_evaluation_scheduler` (which resolves each pending forecast
against the later fare on the same booking curve) and `forecast_evaluator` (which
aggregates the resolved outcomes). Neither reports zeros for an unmeasured
forecast — they report NaN with the row counts.

So the returned dict has no `metrics` key. A caller wanting forecast accuracy
must read the evaluated outcomes, not this.
"""

import logging
import math
from typing import Dict, Any, List, Optional
from opentelemetry import metrics

from backend.domain.market_snapshot import MarketSnapshot

logger = logging.getLogger(__name__)

# OpenTelemetry metrics
meter = metrics.get_meter("skymind.consistency_validator")

deviation_gauge = meter.create_gauge(
    name="prediction_market_deviation_rupees",
    description="Absolute price difference between predicted fare and observed lowest fare"
)
anomalies_counter = meter.create_counter(
    name="prediction_anomalies_total",
    description="Total anomalous predictions observed"
)
missing_live_counter = meter.create_counter(
    name="prediction_missing_live_data_total",
    description="Counter for missing live search parameters during prediction validation"
)

class PredictionConsistencyValidator:
    @staticmethod
    def validate_consistency(
        predicted_price: float,
        market_snapshot: MarketSnapshot,
        forecast: List[Dict[str, Any]],
        route: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Observational plausibility checks on one prediction; records telemetry.

        Args:
            predicted_price: The fare the model quoted.
            market_snapshot: The live market it is being checked against.
            forecast: The formatted per-day forecast, for the day-1 agreement check.
            route: `"ORIGIN-DESTINATION"`, used only as a telemetry label. The
                snapshot does not carry the route, so without this the deviation
                gauge cannot say which route it measured.

        Returns:
            `anomalous`, `reasons`, and — when live fares were available —
            `deviation`. No forecast-error metrics; see the module docstring.
        """
        anomalous = False
        anomalies_reasons = []

        # Check if live price details exist
        lowest = market_snapshot.lowest_fare
        highest = market_snapshot.highest_fare

        if math.isnan(lowest) or math.isnan(highest):
            missing_live_counter.add(1)
            logger.warning("No live prices present in MarketSnapshot; skipping deviation validations.")
            return {"anomalous": False, "reasons": ["Missing live market price benchmarks."]}

        # Calculate deviation from lowest observed live fare
        deviation = abs(predicted_price - lowest)
        # The origin label used to be read as
        # `market_snapshot.airline_distribution.get("origin", "NA")`.
        # `MarketSnapshot` has no route field at all, and `airline_distribution`
        # maps airline code -> flight count, so that lookup could never hit and
        # every point in this gauge was labelled `origin="NA"` — one
        # indistinguishable series for every route in the system. The route is
        # known at the call site, so it is passed in.
        deviation_gauge.set(deviation, {
            "route": route or "unknown",
            "provider": market_snapshot.provider
        })
        
        # 1. Prediction price exceeds bounds significantly (anomaly triggers)
        if predicted_price > highest * 2.5:
            anomalous = True
            anomalies_reasons.append(f"Predicted price (₹{predicted_price}) is > 2.5x the highest live fare (₹{highest}).")
        if predicted_price < lowest * 0.3:
            anomalous = True
            anomalies_reasons.append(f"Predicted price (₹{predicted_price}) is < 30% of the lowest live fare (₹{lowest}).")
            
        # 2. Check forecast trends consistency
        if forecast:
            first_day_price = forecast[0].get("price", predicted_price)
            forecast_deviation = abs(first_day_price - predicted_price)
            if forecast_deviation > predicted_price * 0.8:
                anomalous = True
                anomalies_reasons.append(f"Forecast day 1 (₹{first_day_price}) deviates > 80% from prediction (₹{predicted_price}).")
                
        # Forecast error (MAE/RMSE/MAPE/bias) was reported from here, from five
        # locals fixed at 0.0 — see the module docstring. It is measured by
        # `forecast_evaluation_scheduler` once the horizon has elapsed and a
        # realised fare exists, and aggregated by `forecast_evaluator`.

        if anomalous:
            # `prediction_anomalies_total` was declared and never incremented, so
            # the counter that exists to alert on anomalous predictions read 0
            # however many were found. One increment per anomalous *prediction*,
            # which is what the counter's description promises — not one per
            # reason, since two rules can fire on the same prediction and that
            # would inflate the count above the number of predictions made.
            anomalies_counter.add(1, {
                "route": route or "unknown",
                "provider": market_snapshot.provider,
            })

        logger.info(
            f"Prediction Consistency Validator run — Predicted: ₹{predicted_price}, Current Lowest: ₹{lowest}, "
            f"Anomalous: {anomalous}, Reasons: {anomalies_reasons}"
        )

        return {
            "anomalous": anomalous,
            "deviation": round(deviation, 2),
            "reasons": anomalies_reasons,
        }
