"""Focused Booking Recommendation Engine Strategy."""

import math
from typing import List, Dict, Any, Optional, Tuple
from backend.domain.canonical_forecast import TimelinePointDomain
from backend.services.forecast.savings_calculator import SavingsCalculator


class RecommendationEngineStrategy:
    """Evaluates forecast timeline points against live market fare to issue booking advice."""

    def evaluate_recommendation(
        self,
        current_fare: Optional[float],
        timeline: List[TimelinePointDomain]
    ) -> Tuple[str, List[str], int, str, float, float, float]:
        """Returns (decision, reasons, optimal_horizon, optimal_date, min_fare, abs_savings, pct_savings)."""
        # Degraded / Historical-only fallback when current_fare is unavailable
        if current_fare is None or math.isnan(current_fare) or current_fare <= 0:
            best_pt = min(timeline, key=lambda p: (p.predicted_price, p.horizon_days)) if timeline else None
            best_day = best_pt.horizon_days if best_pt else 0
            best_date = best_pt.booking_date if best_pt else "Today"
            best_price = best_pt.predicted_price if best_pt else 0.0

            return (
                "MONITOR",
                ["Live market fare unavailable. Generating forecast recommendations from historical trends."],
                best_day,
                best_date,
                best_price,
                0.0,
                0.0
            )

        # Find earliest horizon point with the lowest predicted fare (price, horizon_days tie-breaking)
        best_pt = min(timeline, key=lambda p: (p.predicted_price, p.horizon_days))
        best_day = best_pt.horizon_days
        best_date = best_pt.booking_date
        best_price = best_pt.predicted_price

        abs_savings, pct_savings = SavingsCalculator.calculate_savings(current_fare, best_price)

        if best_day == 0 or abs_savings <= 0:
            decision = "BOOK_NOW"
            reasons = [
                "Today's fare is the lowest expected price across all forecast horizons. Waiting is not expected to yield additional savings."
            ]
            optimal_horizon = 0
            expected_min = current_fare
            final_abs_savings = 0.0
            final_pct_savings = 0.0
        else:
            decision = "WAIT"
            reasons = [
                f"The forecast indicates the lowest fare occurs in approximately {best_day} day(s). "
                f"Waiting is expected to save ₹{abs_savings} ({pct_savings}%)."
            ]
            optimal_horizon = best_day
            expected_min = best_price
            final_abs_savings = abs_savings
            final_pct_savings = pct_savings

        return (
            decision,
            reasons,
            optimal_horizon,
            best_date,
            expected_min,
            final_abs_savings,
            final_pct_savings
        )
