"""Confidence Scoring Engine for Canonical Forecast System."""

from typing import Dict, Any, Optional

from backend.services.confidence_policy import (
    clamp_to_accuracy_scale,
    quality_multiplier,
)


class ConfidenceEngine:
    """Computes unified confidence scores and component breakdowns."""

    def compute_confidence(
        self,
        model_accuracy: Optional[float],
        snapshot_quality: Optional[float],
        is_live_market: bool
    ) -> Dict[str, Any]:
        """Calculate overall confidence and its component breakdown.

        Every parameter is required. They used to default to
        `model_accuracy: float = 95.0` and `snapshot_quality: float = 1.0`, so a
        caller that forgot to pass a measurement got the highest scores the
        function can produce, and the response was indistinguishable from one
        backed by a real evaluation.

        Two computations were removed:

        `max(70.0, min(99.0, model_accuracy))` — the floor rewrote any figure
        below 70 as 70, so a model measured at 42 published as 70; the ceiling
        rewrote 100 as 99. Bounding to the 0-100 scale of the field is all that is
        left, in `clamp_to_accuracy_scale`.

        `max(0.5, min(1.0, snapshot_quality)) if is_live_market else 0.85` — with
        no live market this paid 0.85 while a live market of the worst measurable
        quality paid 0.5, so losing the data source raised the published
        confidence by 70%. The ordering now lives in `confidence_policy` and is
        checked at import there.

        `model_accuracy` of None means no training run recorded a metric. The
        result is a null confidence, not a low one; the two are different claims
        and the response distinguishes them.
        """
        eff_model_acc = clamp_to_accuracy_scale(model_accuracy)
        eff_quality = quality_multiplier(snapshot_quality, is_live_market)

        if eff_model_acc is None:
            return {
                "overall_confidence": None,
                "breakdown": {
                    "model_validation_score": None,
                    "market_data_quality": round(eff_quality, 2),
                    "prediction_reliability": None
                }
            }

        overall_conf = round(eff_model_acc * eff_quality, 2)

        return {
            "overall_confidence": overall_conf,
            "breakdown": {
                "model_validation_score": round(eff_model_acc, 2),
                "market_data_quality": round(eff_quality, 2),
                "prediction_reliability": overall_conf
            }
        }
