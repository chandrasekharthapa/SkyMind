"""Final deterministic booking decision agent."""

from __future__ import annotations

from .demand_agent import analyze_demand
from .pricing_agent import analyze_pricing
from .risk_agent import analyze_risk


def make_decision(snapshot: dict, forecast: list[dict]) -> dict:
    current_price = float(snapshot["current_price"])
    pricing = analyze_pricing(current_price, forecast)
    demand = analyze_demand(
        int(snapshot["days_until_departure"]),
        int(snapshot["seats_available"]),
        float(snapshot["demand_score"]),
    )
    risk = analyze_risk(forecast, current_price)

    buy_score = 0.0
    buy_score += max(0.0, pricing["score"]) * 0.44
    buy_score += demand["score"] * 0.36
    buy_score += risk["score"] * 0.20
    wait_score = max(0.0, -pricing["score"]) * 0.58 + (1.0 - demand["score"]) * 0.28

    decision = "BOOK NOW" if buy_score >= wait_score else "WAIT"
    margin = abs(buy_score - wait_score)
    confidence = round(min(0.94, max(0.52, 0.56 + margin * 0.55)), 2)

    reasons = [pricing["reason"], demand["reason"], risk["reason"]]
    if decision == "BOOK NOW":
        reasons.append("The combined agent score favors locking the fare before upward pressure compounds.")
    else:
        reasons.append("The combined agent score leaves enough room to monitor for a better fare.")

    return {
        "decision": decision,
        "confidence": confidence,
        "reasons": reasons,
    }
