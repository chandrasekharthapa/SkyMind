"""Demand urgency and seat-pressure agent."""

from __future__ import annotations


def analyze_demand(days_until_departure: int, seats_available: int, demand_score: float) -> dict:
    urgency = 1.0 / max(days_until_departure + 1, 1)
    seat_pressure = max(0.0, min(1.0, (32 - seats_available) / 32))
    score = min(1.0, urgency * 2.4 + seat_pressure * 0.55 + demand_score * 0.35)

    if score >= 0.62:
        label = "HIGH"
        reason = "Demand pressure is high from timing and remaining seat inventory."
    elif score >= 0.34:
        label = "MEDIUM"
        reason = "Demand pressure is moderate; inventory is worth watching."
    else:
        label = "LOW"
        reason = "Demand pressure is low enough to allow more waiting room."

    return {"demand": label, "score": round(score, 4), "reason": reason}
