"""Forecast volatility risk agent."""

from __future__ import annotations

import statistics


def analyze_risk(forecast: list[dict], current_price: float) -> dict:
    prices = [float(point["price"]) for point in forecast[:30]]
    if len(prices) < 2:
        return {"risk": "LOW", "score": 0.0, "reason": "Volatility is limited in the forecast."}

    volatility = statistics.pstdev(prices) / max(current_price, 1.0)
    spread = (max(prices) - min(prices)) / max(current_price, 1.0)
    score = min(1.0, volatility * 4.0 + spread * 0.8)

    if score >= 0.5:
        label = "HIGH"
        reason = "Forecast volatility is high, increasing price-move risk."
    elif score >= 0.24:
        label = "MEDIUM"
        reason = "Forecast volatility is moderate across the next 30 days."
    else:
        label = "LOW"
        reason = "Forecast volatility is low."

    return {"risk": label, "score": round(score, 4), "reason": reason}
