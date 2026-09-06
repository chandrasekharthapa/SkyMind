"""Domain Models & Dataclasses for Canonical Forecast System."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class TimelinePointDomain:
    horizon_days: int
    booking_date: str
    predicted_price: float
    lower_bound: float
    upper_bound: float
    # None means no training run recorded an evaluation metric for the model that
    # produced this point. That is a different claim from a low score, so it is
    # published as null rather than collapsed to a number.
    confidence_score: Optional[float]
    is_optimal: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "booking_date": self.booking_date,
            "predicted_price": round(float(self.predicted_price), 2),
            "lower_bound": round(float(self.lower_bound), 2),
            "upper_bound": round(float(self.upper_bound), 2),
            "confidence_score": (
                None if self.confidence_score is None
                else round(float(self.confidence_score), 2)
            ),
            "is_optimal": self.is_optimal,
            "metadata": self.metadata or {"currency": "INR"}
        }


@dataclass(frozen=True)
class ForecastDiagnostics:
    invariants_passed: bool
    violations: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0


@dataclass(frozen=True)
class CanonicalForecastDomain:
    current_fare: Optional[float]
    expected_minimum_fare: float
    optimal_horizon_days: int
    optimal_booking_date: str
    recommendation_decision: str  # "BOOK_NOW", "WAIT", or "MONITOR"
    recommendation_reasons: List[str]
    calculated_savings: float
    percentage_savings: float
    # None when no horizon's model has a recorded evaluation metric. See
    # services/confidence_policy.py for why this is never defaulted.
    confidence_score: Optional[float]
    confidence_breakdown: Dict[str, Optional[float]]
    timeline: List[TimelinePointDomain]
    diagnostics: ForecastDiagnostics
    forecast_metadata: Dict[str, Any] = field(default_factory=dict)
    is_valid: bool = True
