"""Single-source Savings Calculator for Forecast System."""

import math
from typing import Tuple, Optional


class SavingsCalculator:
    """Provides pure, deterministic savings calculations."""

    @staticmethod
    def calculate_savings(current_fare: Optional[float], expected_min_fare: float) -> Tuple[float, float]:
        """Calculates (absolute_savings_rupees, percentage_savings).
        
        Formula:
          If current_fare is None, 0.0, or <= expected_min_fare -> (0.0, 0.0)
          Else -> (current_fare - expected_min_fare, ((current_fare - expected_min_fare) / current_fare) * 100.0)
        """
        if current_fare is None or math.isnan(current_fare) or current_fare <= 0:
            return (0.0, 0.0)

        if current_fare <= expected_min_fare:
            return (0.0, 0.0)

        raw_savings = current_fare - expected_min_fare
        abs_savings = round(float(raw_savings), 2)
        pct_savings = round(float((raw_savings / current_fare) * 100.0), 1)

        return (abs_savings, pct_savings)
