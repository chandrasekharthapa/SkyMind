"""Pricing trend agent."""

from __future__ import annotations


def analyze_pricing(current_price: float, forecast: list[dict]) -> dict:
    if not forecast:
        return {"trend": "STABLE", "score": 0.0, "reason": "No forecast movement detected."}

    future_prices = [float(point["price"]) for point in forecast[:14]]
    avg_future = sum(future_prices) / len(future_prices)
    delta_pct = ((avg_future - current_price) / max(current_price, 1.0)) * 100

    if delta_pct >= 4.0:
        trend = "RISING"
        score = min(1.0, delta_pct / 16)
        reason = f"Forecast average is {delta_pct:.1f}% above the current fare."
    elif delta_pct <= -4.0:
        trend = "FALLING"
        score = max(-1.0, delta_pct / 16)
        reason = f"Forecast average is {abs(delta_pct):.1f}% below the current fare."
    else:
        trend = "STABLE"
        score = 0.0
        reason = "Forecast prices are close to the current fare."

    return {"trend": trend, "score": round(score, 4), "reason": reason}
