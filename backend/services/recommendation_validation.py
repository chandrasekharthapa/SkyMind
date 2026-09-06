"""Recommendation Validation Module (Milestone 7).

Verifies BUY, WAIT, MONITOR decisions are consistent with predicted prices, confidence,
expected savings, and forecast horizon. Rejects contradictory recommendations.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RecommendationValidationService:
    def __init__(self):
        pass

    def validate_recommendation(
        self,
        recommendation: Dict[str, Any],
        current_lowest_fare: float,
        predicted_price: float,
        confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """Validate recommendation decision consistency against numerical price trends.

        `confidence` is echoed into the result and is not used in any of the rules
        below. Its default was `95.0`, so a caller that passed no confidence at all
        — which is every caller in this repository, including
        `validate_recommendations_batch` — produced a validation record asserting a
        confidence of 95.0 that no model had measured. The default is None: no
        figure supplied, no figure reported.
        """
        errors = []
        warnings = []

        if not recommendation or not isinstance(recommendation, dict):
            return {"valid": False, "errors": ["Recommendation is empty or missing"]}

        decision = recommendation.get("decision")
        if decision not in ["BUY", "WAIT", "MONITOR"]:
            errors.append(f"Invalid recommendation decision string: {decision}")
            return {"valid": False, "errors": errors}

        pct_change = ((predicted_price - current_lowest_fare) / max(1.0, current_lowest_fare)) * 100.0

        # Rule 1: Contradiction check for BUY (Book Now)
        # BUY is recommended when price is expected to rise sharply (> +3.0%).
        if decision == "BUY" and pct_change < -5.0:
            errors.append(f"Contradictory decision 'BUY' when price is expected to fall by {pct_change:.1f}%")

        # Rule 2: Contradiction check for WAIT
        # WAIT is recommended when price is expected to drop significantly (< -3.0%).
        if decision == "WAIT" and pct_change > 10.0:
            errors.append(f"Contradictory decision 'WAIT' when price is expected to rise by +{pct_change:.1f}%")

        # Rule 3: Contradiction check for MONITOR
        # MONITOR is recommended when price is stable within +/- 5.0%.
        if decision == "MONITOR" and (pct_change > 25.0 or pct_change < -25.0):
            warnings.append(f"Decision 'MONITOR' assigned despite high fare delta ({pct_change:.1f}%)")

        is_valid = len(errors) == 0

        return {
            "valid": is_valid,
            "decision": decision,
            "pct_change": round(pct_change, 2),
            "errors": errors,
            "warnings": warnings,
            "confidence": confidence
        }

    def validate_recommendations_batch(self, rec_batch: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate a batch of recommendation payloads for consistency.

        An item that does not carry both a fare and a prediction is counted as an
        error rather than validated against a substituted figure. This was
        `item.get("lowest_fare", 5000.0)` and `item.get("predicted_price", 5000.0)`:
        an item missing both got the same number for each, `pct_change` came out
        exactly 0.0, and every rule below is a threshold on `pct_change` — so no
        rule could fire and the item passed. A payload with no numbers in it was
        the easiest way to be judged consistent.
        """
        valid_count = 0
        error_count = 0
        missing_inputs = 0

        for item in rec_batch:
            fare = item.get("lowest_fare")
            predicted = item.get("predicted_price")
            if not isinstance(fare, (int, float)) or not isinstance(predicted, (int, float)):
                missing_inputs += 1
                error_count += 1
                continue
            res = self.validate_recommendation(
                recommendation=item.get("recommendation", {}),
                current_lowest_fare=float(fare),
                predicted_price=float(predicted),
            )
            if res["valid"]:
                valid_count += 1
            else:
                error_count += 1

        total = len(rec_batch)
        consistency_ratio = float(valid_count / max(1, total))

        return {
            "valid": error_count == 0,
            "total_validated": total,
            "valid_count": valid_count,
            "error_count": error_count,
            "missing_inputs_count": missing_inputs,
            "consistency_ratio": round(consistency_ratio, 4)
        }


recommendation_validation_service = RecommendationValidationService()
