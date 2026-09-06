"""Demand urgency and seat-pressure agent.

Complying with Zero Synthetic Feature Policy: handles missing seats/demand gracefully.
"""

from __future__ import annotations
import math

def analyze_demand(days_until_departure: int, seats_available: int | None, demand_score: float | None) -> dict:
    urgency = 1.0 / max(days_until_departure + 1, 1)
    
    # Calculate seat pressure if available
    seat_pressure = 0.0
    has_seats = False
    if seats_available is not None and not (isinstance(seats_available, float) and math.isnan(seats_available)):
        seat_pressure = max(0.0, min(1.0, (32 - seats_available) / 32))
        has_seats = True
        
    # Check demand score
    has_demand = False
    d_score = 0.0
    if demand_score is not None and not (isinstance(demand_score, float) and math.isnan(demand_score)):
        d_score = demand_score
        has_demand = True
        
    # Scale score calculation based on available components
    if has_seats and has_demand:
        score = min(1.0, urgency * 2.4 + seat_pressure * 0.55 + d_score * 0.35)
    elif has_seats:
        score = min(1.0, urgency * 2.4 + seat_pressure * 0.55)
    elif has_demand:
        score = min(1.0, urgency * 2.4 + d_score * 0.35)
    else:
        score = min(1.0, urgency * 2.4)

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
