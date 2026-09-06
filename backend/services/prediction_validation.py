"""Prediction Validation Module (Milestone 3).

Validates predicted price, confidence intervals, recommendations, and forecast trajectories.
Ensures numerical stability, absence of constant outputs across routes, and non-negativity.
"""

import logging
import math
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Responses needed before route diversity means anything, and the fraction of
# them that must carry distinct prices. See `validate_route_diversity` for why
# the comparison is strict.
MIN_ROUTES_FOR_DIVERSITY = 2
MIN_UNIQUE_PRICE_RATIO = 0.50


class PredictionValidationService:
    def __init__(self):
        pass

    def validate_prediction_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Validate an API prediction response dictionary."""
        errors = []
        warnings = []

        if not response or not isinstance(response, dict):
            return {"valid": False, "errors": ["Response is empty or invalid type"]}

        # 1. Price non-negativity & finite bounds
        predicted_price = response.get("predicted_price")
        if predicted_price is None or not isinstance(predicted_price, (int, float)):
            errors.append("predicted_price is missing or non-numeric")
        elif predicted_price <= 0 or math.isnan(predicted_price) or math.isinf(predicted_price):
            errors.append(f"predicted_price must be finite and positive (>0), got: {predicted_price}")

        # 2. Forecast trajectory numerical stability & confidence bounds
        forecast = response.get("forecast", [])
        if not forecast or not isinstance(forecast, list):
            errors.append("forecast array is missing or empty")
        else:
            prices = []
            for point in forecast:
                pr = point.get("price")
                lower = point.get("lower")
                upper = point.get("upper")

                if pr is None or lower is None or upper is None:
                    errors.append(f"Forecast point missing price/lower/upper: {point}")
                    continue

                if lower > pr or pr > upper:
                    errors.append(f"Confidence bound violated: lower ({lower}) <= price ({pr}) <= upper ({upper})")

                if pr <= 0:
                    errors.append(f"Forecast price must be positive: {pr}")

                prices.append(pr)

            # Check for constant fallback output (e.g., exactly constant prices across all horizons)
            if len(prices) >= 3 and len(set(prices)) == 1:
                warnings.append("Forecast trajectory contains constant fallback output across all horizons")

        # 3. Recommendation decision validity
        rec = response.get("recommendation", {})
        decision = rec.get("decision") if isinstance(rec, dict) else None
        if decision not in ["BUY", "WAIT", "MONITOR"]:
            errors.append(f"Invalid recommendation decision: {decision}")

        is_valid = len(errors) == 0

        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "predicted_price": predicted_price,
            "recommendation_decision": decision,
            "forecast_horizons_count": len(forecast) if isinstance(forecast, list) else 0
        }

    def validate_route_diversity(self, route_responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Verify that predictions across different routes produce distinct outputs.

        `valid` is None when the check could not be measured, and callers must
        distinguish that from True. It used to return `{"valid": True}` for a list
        of nought or one response — the two cases where diversity is undefined —
        so the check that exists to catch a model emitting one number for every
        route reported success precisely when it had been given nothing to
        compare.

        The bound is `> MIN_UNIQUE_PRICE_RATIO`, and total collapse fails
        independently of it. It was `unique_ratio >= 0.50`, which cannot bind at
        the smallest input this check accepts: two routes answered with the *same*
        price give a ratio of exactly 0.50 and passed. A threshold that a complete
        collapse satisfies is the defect this check was written to detect. At four
        routes the old bound likewise tolerated half of them being duplicates.

        A response carrying no numeric `predicted_price` is neither distinct nor a
        duplicate; it is a measurement that did not happen, so it is excluded from
        the ratio and counted separately rather than quietly depressing it.
        """
        if not route_responses or len(route_responses) < MIN_ROUTES_FOR_DIVERSITY:
            return {
                "valid": None,
                "measured": False,
                "reason": (
                    f"route diversity needs at least {MIN_ROUTES_FOR_DIVERSITY} "
                    f"predictions to compare; got {len(route_responses or [])}"
                ),
                "total_routes_tested": len(route_responses or []),
            }

        predicted_prices = set()
        unpriced = 0
        for resp in route_responses:
            price = resp.get("predicted_price") if isinstance(resp, dict) else None
            if not isinstance(price, (int, float)) or isinstance(price, bool):
                unpriced += 1
                continue
            predicted_prices.add(round(float(price), 2))

        priced = len(route_responses) - unpriced
        if priced < MIN_ROUTES_FOR_DIVERSITY:
            return {
                "valid": None,
                "measured": False,
                "reason": (
                    f"only {priced} of {len(route_responses)} response(s) carry a "
                    f"numeric predicted_price, so there is nothing to compare"
                ),
                "total_routes_tested": len(route_responses),
                "unpriced_count": unpriced,
            }

        unique_ratio = len(predicted_prices) / priced
        is_route_specific = (
            len(predicted_prices) > 1 and unique_ratio > MIN_UNIQUE_PRICE_RATIO
        )

        return {
            "valid": is_route_specific,
            "measured": True,
            "total_routes_tested": len(route_responses),
            "priced_count": priced,
            "unpriced_count": unpriced,
            "unique_price_count": len(predicted_prices),
            "uniqueness_ratio": round(unique_ratio, 4),
            "is_route_specific": is_route_specific
        }


prediction_validation_service = PredictionValidationService()
