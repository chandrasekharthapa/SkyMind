"""Forecast Assembler coordinating timeline building, scoring, and invariant validation."""

import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from backend.domain.canonical_forecast import CanonicalForecastDomain, TimelinePointDomain, ForecastDiagnostics
from backend.services.forecast.timeline_builder import TimelineBuilder
from backend.services.forecast.recommendation_engine import RecommendationEngineStrategy
from backend.services.forecast.confidence_engine import ConfidenceEngine
from backend.services.forecast.forecast_validator import ForecastValidationEngine


class ForecastAssembler:
    """Assembles and validates canonical forecast domain objects."""

    def __init__(
        self,
        timeline_builder: Optional[TimelineBuilder] = None,
        recommendation_strategy: Optional[RecommendationEngineStrategy] = None,
        confidence_engine: Optional[ConfidenceEngine] = None,
        validation_engine: Optional[ForecastValidationEngine] = None
    ):
        self.timeline_builder = timeline_builder or TimelineBuilder()
        self.recommendation_strategy = recommendation_strategy or RecommendationEngineStrategy()
        self.confidence_engine = confidence_engine or ConfidenceEngine()
        self.validation_engine = validation_engine or ForecastValidationEngine()

    def assemble(
        self,
        formatted_forecast: List[Dict[str, Any]],
        current_fare: Optional[float],
        model_accuracy: Optional[float],
        snapshot_quality: Optional[float],
        is_live_market: bool
    ) -> CanonicalForecastDomain:
        """Assembles CanonicalForecastDomain and validates all mathematical invariants.

        `model_accuracy` and `snapshot_quality` used to default to 95.0 and 1.0.
        They are required now: a caller with no measurement must say so by passing
        None, which produces a null confidence rather than a high one.

        `is_live_market` used to be derived here as `current_fare is not None and
        current_fare > 0`, while `prediction_service` independently derived the
        same concept as `total_live_flights > 0 and not isnan(lowest_fare)`. The
        two disagree whenever a fare comes from recorded history with no live
        flights in the snapshot, and the disagreement fed a confidence multiplier.
        The caller that observed the market now states it once.
        """
        start_time = time.time()

        # 1. Compute Confidence
        conf_res = self.confidence_engine.compute_confidence(
            model_accuracy=model_accuracy,
            snapshot_quality=snapshot_quality,
            is_live_market=is_live_market
        )

        # 2. Build Timeline Points
        timeline_pts = self.timeline_builder.build_timeline(
            formatted_forecast=formatted_forecast,
            current_fare=current_fare,
            base_confidence=conf_res["overall_confidence"]
        )

        # 3. Evaluate Booking Recommendation & Savings
        (
            decision,
            reasons,
            optimal_horizon,
            optimal_date,
            expected_min,
            abs_savings,
            pct_savings
        ) = self.recommendation_strategy.evaluate_recommendation(
            current_fare=current_fare,
            timeline=timeline_pts
        )

        # Mark optimal point in timeline & attach point metadata
        updated_timeline = []
        for pt in timeline_pts:
            is_opt = (pt.horizon_days == optimal_horizon)
            updated_timeline.append(TimelinePointDomain(
                horizon_days=pt.horizon_days,
                booking_date=pt.booking_date,
                predicted_price=pt.predicted_price,
                lower_bound=pt.lower_bound,
                upper_bound=pt.upper_bound,
                confidence_score=pt.confidence_score,
                is_optimal=is_opt,
                metadata={"currency": "INR", "is_optimal": is_opt}
            ))

        # 4. Enforce Mathematical Invariants
        diagnostics = self.validation_engine.validate(
            current_fare=current_fare,
            expected_min_fare=expected_min,
            optimal_horizon_days=optimal_horizon,
            decision=decision,
            calculated_savings=abs_savings,
            timeline=updated_timeline
        )

        elapsed_ms = round((time.time() - start_time) * 1000.0, 2)

        # `"model_version": "XGBoost v2"` used to sit here as a literal, beside a
        # `"forecast_version"` literal, in a block named metadata. It was not a
        # version: it never changed when a model was retrained, it named an
        # algorithm rather than an artifact, and it was the only provenance the
        # forecast response carried. Each point in `formatted_forecast` already
        # carries the version of the artifact that produced it — see
        # `PredictionFormatter.format_forecast` — so the versions are read off the
        # points instead of asserted about them.
        #
        # They are read as a set, not a scalar, because each horizon is served by
        # its own artifact: a curve can legitimately span several versions, and
        # collapsing that to one string is how the wrong one gets published. A
        # single value appears under `model_version` only when it is unambiguous;
        # otherwise that field is null and `model_versions` lists what was used.
        def _versions(key: str) -> List[str]:
            seen = {
                str(p.get(key)) for p in (formatted_forecast or [])
                if isinstance(p, dict) and p.get(key)
            }
            return sorted(seen)

        model_versions = _versions("model_version")
        schema_versions = _versions("feature_schema_version")

        forecast_meta = {
            # The version of this response's own shape, maintained by hand. It
            # describes the assembler's output contract, not the model.
            "forecast_version": "2.0.0",
            "model_version": model_versions[0] if len(model_versions) == 1 else None,
            "model_versions": model_versions,
            "feature_schema_version": schema_versions[0] if len(schema_versions) == 1 else None,
            "provider": "SkyMind Intelligence Engine",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "currency": "INR"
        }

        return CanonicalForecastDomain(
            current_fare=current_fare,
            expected_minimum_fare=round(float(expected_min), 2),
            optimal_horizon_days=optimal_horizon,
            optimal_booking_date=optimal_date,
            recommendation_decision=decision,
            recommendation_reasons=reasons,
            calculated_savings=abs_savings,
            percentage_savings=pct_savings,
            confidence_score=conf_res["overall_confidence"],
            confidence_breakdown=conf_res["breakdown"],
            timeline=updated_timeline,
            diagnostics=ForecastDiagnostics(
                invariants_passed=diagnostics.invariants_passed,
                violations=diagnostics.violations,
                execution_time_ms=elapsed_ms
            ),
            forecast_metadata=forecast_meta,
            is_valid=diagnostics.invariants_passed
        )
