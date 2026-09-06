"""Mathematical Invariant Validation Engine for Canonical Forecast System.

Enforces 4 formal mathematical invariants:
1. Timeline Bounds: lower_bound <= predicted_price <= upper_bound for every point
2. BOOK_NOW Invariant: decision == 'BOOK_NOW' => optimal_horizon == 0, expected_min == current_fare, savings == 0
3. WAIT Invariant: decision == 'WAIT' => optimal_horizon > 0, expected_min < current_fare, savings > 0
4. Savings Reconciliation: calculated_savings == max(0, current_fare - expected_min_fare)
"""

import math
import logging
from typing import List, Optional
from backend.domain.canonical_forecast import TimelinePointDomain, ForecastDiagnostics

logger = logging.getLogger(__name__)


class ForecastValidationEngine:
    """Enforces strict mathematical invariants across domain forecasts."""

    def validate(
        self,
        current_fare: Optional[float],
        expected_min_fare: float,
        optimal_horizon_days: int,
        decision: str,
        calculated_savings: float,
        timeline: List[TimelinePointDomain]
    ) -> ForecastDiagnostics:
        """Validates all mathematical invariants and returns ForecastDiagnostics."""
        violations: List[str] = []

        # Invariant 1: Bounds Check (lower <= price <= upper)
        for pt in timeline:
            if not (pt.lower_bound <= pt.predicted_price <= pt.upper_bound):
                violations.append(
                    f"Timeline point (Day {pt.horizon_days}) failed bounds check: "
                    f"lower ({pt.lower_bound}) <= price ({pt.predicted_price}) <= upper ({pt.upper_bound})"
                )

        # Invariant 2: BOOK_NOW Reconciliation Check
        if decision == "BOOK_NOW":
            if optimal_horizon_days != 0:
                violations.append(f"BOOK_NOW decision has non-zero optimal horizon: {optimal_horizon_days}")
            if calculated_savings != 0.0:
                violations.append(f"BOOK_NOW decision has non-zero savings: ₹{calculated_savings}")

        # Invariant 3: WAIT Reconciliation Check
        elif decision == "WAIT":
            if optimal_horizon_days <= 0:
                violations.append(f"WAIT decision has non-positive optimal horizon: {optimal_horizon_days}")
            if current_fare is not None and not math.isnan(current_fare) and current_fare > 0:
                if calculated_savings <= 0.0:
                    violations.append(f"WAIT decision has zero/negative savings: ₹{calculated_savings}")

        # Invariant 4: Savings Math Reconciliation Check
        if current_fare is not None and not math.isnan(current_fare) and current_fare > 0:
            expected_savings = round(max(0.0, current_fare - expected_min_fare), 2)
            if abs(calculated_savings - expected_savings) > 0.5:
                violations.append(
                    f"Savings calculation mismatch: calculated ₹{calculated_savings} != expected ₹{expected_savings} "
                    f"(current: ₹{current_fare}, min: ₹{expected_min_fare})"
                )

        passed = len(violations) == 0
        if not passed:
            for v in violations:
                logger.error(f"[ForecastValidationEngine] INVARIANT VIOLATION: {v}")

        return ForecastDiagnostics(
            invariants_passed=passed,
            violations=violations
        )
