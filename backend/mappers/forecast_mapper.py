"""Forecast Mapper converting Domain models to serialized API DTOs."""

from typing import Dict, Any
from backend.domain.canonical_forecast import CanonicalForecastDomain


class ForecastMapper:
    """Maps CanonicalForecastDomain domain objects to serialized JSON DTO payloads."""

    @staticmethod
    def to_dto(domain: CanonicalForecastDomain) -> Dict[str, Any]:
        """Serializes CanonicalForecastDomain into API response DTO."""
        return {
            "current_fare": round(float(domain.current_fare), 2) if domain.current_fare is not None else None,
            "expected_minimum_fare": round(float(domain.expected_minimum_fare), 2),
            "optimal_booking_horizon": domain.optimal_horizon_days,
            "optimal_booking_date": domain.optimal_booking_date,
            "recommendation_decision": domain.recommendation_decision,
            "recommendation_reasons": domain.recommendation_reasons,
            "calculated_savings": round(float(domain.calculated_savings), 2),
            "percentage_savings": round(float(domain.percentage_savings), 1),
            # None when no training run recorded a metric for any horizon. The
            # field is nullable on the wire for the same reason it is nullable in
            # the domain: "unmeasured" is a different claim from "measured low",
            # and collapsing the two is how a default became indistinguishable
            # from a measurement.
            "confidence_score": (
                None if domain.confidence_score is None
                else round(float(domain.confidence_score), 2)
            ),
            "confidence_breakdown": domain.confidence_breakdown,
            "timeline": [pt.to_dict() for pt in domain.timeline],
            "diagnostics": {
                "invariants_passed": domain.diagnostics.invariants_passed,
                "violations": domain.diagnostics.violations,
                "execution_time_ms": domain.diagnostics.execution_time_ms
            },
            "forecast_metadata": domain.forecast_metadata or {},
            "is_valid": domain.is_valid
        }
