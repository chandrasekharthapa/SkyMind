"""Prediction Formatter Layer.

Formats ML model forecast lists, decision recommendations, trends,
confidence metrics, and price intelligence.
"""

from typing import List, Dict, Any, Optional
import numpy as np

class PredictionFormatter:
    @staticmethod
    def calculate_trend(forecast: List[Dict[str, Any]]) -> tuple[str, float, float]:
        """Determine trend, change percentage, and probability metric based on forecast progression."""
        change_percent = 0.0
        trend = "STABLE"
        prob_increase = 0.5

        if len(forecast) >= 2:
            first = float(forecast[0]["price"])
            last = float(forecast[-1]["price"])
            if first > 0:
                change_percent = ((last - first) / first) * 100

            if change_percent > 3.0:
                trend = "RISING"
                prob_increase = 0.75 + min(0.2, change_percent / 100)
            elif change_percent < -3.0:
                trend = "FALLING"
                prob_increase = 0.25 - min(0.2, abs(change_percent) / 100)
            else:
                trend = "STABLE"
                prob_increase = 0.5 + (change_percent / 10)

        prob_increase = max(0.0, min(1.0, prob_increase))
        return trend, round(change_percent, 2), round(prob_increase, 2)

    @staticmethod
    def compute_market_status(db_prices: List[float]) -> Optional[str]:
        """Compute market status from actual historical standard deviation volatility."""
        if not db_prices or len(db_prices) < 3:
            return None
        avg = sum(db_prices) / len(db_prices)
        if avg <= 0:
            return "STABLE"
        # Standard deviation
        variance = sum((p - avg) ** 2 for p in db_prices) / len(db_prices)
        std_dev = variance ** 0.5
        volatility_ratio = std_dev / avg
        return "VOLATILE" if volatility_ratio > 0.08 else "STABLE"

    @staticmethod
    def format_forecast(
        forecast: List[Dict[str, Any]],
        model_version: Optional[str] = None,
        feature_schema_version: Optional[str] = None,
        confidence_by_horizon: Optional[Dict[int, Optional[float]]] = None
    ) -> List[Dict[str, Any]]:
        """Round forecasted price bounds and attach each horizon's own confidence.

        The two version defaults were `"1.0.0"`, a string that matches no artifact
        in the system — everything else says "2.0.0" — so a caller who omitted them
        stamped every point with a version that had never been trained. They are
        `None` now: a point whose producer did not state a version says so. The one
        production caller, `forecast_engine`, passes the registry's values, and the
        assembler reads the versions back off these points to build the response's
        provenance block, so a wrong default here becomes a wrong published claim.

        The signature used to be `confidence: float = 70.0` and this method
        published `confidence * (1.0 - day * 0.02)`: one figure for the whole
        curve, decayed by two percentage points per day. Both halves were
        invented. The caller could not supply a real figure — it was resolving it
        from a dict lookup that always missed, so the value was a constant 95.0 —
        and the decay asserted a relationship between horizon and accuracy that
        the trained models contradict: the shipped 1d artifact recorded a higher
        100-MAPE figure than the 0d one.

        Each horizon now carries the metric its own model recorded, or null where
        no metric exists. Null is a valid published value here; it means "this
        horizon's model has no recorded evaluation", which is a different
        statement from a low score.

        `interval_basis` is passed through from the predictor when present. The
        bounds used to be `price ± max(120, 6% of price)`, and nothing in the
        response distinguished that from a measured interval; the basis block
        names the residual percentiles the width came from and how many residuals
        they were measured on, so a reader can tell. It is absent — not
        substituted — for a producer that does not supply one.
        """
        by_horizon = confidence_by_horizon or {}
        formatted = []
        for item in forecast:
            price_val = round(float(item["price"]), 2)
            day = int(item["day"])
            conf = by_horizon.get(day)
            point = {
                "day": day,
                "date": str(item["date"]),
                "price": price_val,
                "lower": round(float(item["lower"]), 2),
                "upper": round(float(item["upper"]), 2),
                "forecast_price": price_val,
                "forecast_timestamp": f"{item['date']}T12:00:00Z",
                "prediction_horizon": day,
                "confidence": None if conf is None else round(float(conf), 2),
                "model_version": model_version,
                "feature_schema_version": feature_schema_version
            }
            basis = item.get("interval_basis")
            if isinstance(basis, dict):
                point["interval_basis"] = basis
            formatted.append(point)
        return formatted

    @staticmethod
    def format_decision(decision: Dict[str, Any], trend: str, prob_increase: float) -> Dict[str, Any]:
        """Construct the decision output structure with explanations based on trend and probability."""
        reasons = []
        action = "WAIT"

        if prob_increase < 0.40 or trend == "FALLING":
            action = "WAIT"
            reasons.append(
                f"Price trend is currently {trend.lower()}. {int(prob_increase*100)}% probability of price increase detected. Model recommends waiting for the optimal window."
            )
        elif prob_increase >= 0.65 and trend == "RISING":
            action = "BOOK NOW"
            reasons.append(
                f"Price trend is currently {trend.lower()}. {int(prob_increase*100)}% probability of price increase detected. Model recommends booking immediately."
            )
        else:
            action = "WAIT"
            reasons.append(
                f"Price trend is currently {trend.lower()}. {int(prob_increase*100)}% probability of price increase detected. Model recommends monitoring the fare."
            )

        conf_val = decision.get("confidence")
        if conf_val is not None:
            val = float(conf_val)
            if val <= 1.0 and val > 0:
                val = val * 100.0
            conf_percent = round(max(0.0, min(100.0, val)), 2)
        else:
            conf_percent = None

        return {
            "decision": action,
            "reasons": reasons,
            "confidence": conf_percent
        }
