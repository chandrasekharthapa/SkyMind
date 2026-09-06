"""Final deterministic booking decision agent.

Combines the pricing, demand and risk agents into one BOOK NOW / WAIT verdict.

The weights below (0.44 / 0.36 / 0.20 for the buy side, 0.58 / 0.28 for the wait
side) are hand-chosen, not fitted. That is stated here because the function used
to publish a `confidence` derived from them, which read as a calibrated
probability; see the return block.
"""

from __future__ import annotations
import math

from backend.utils.exceptions import PredictionUnavailable

from .demand_agent import analyze_demand
from .pricing_agent import analyze_pricing
from .risk_agent import analyze_risk


def make_decision(snapshot: dict, forecast: list[dict]) -> dict:
    current_price = float(snapshot["current_price"])
    pricing = analyze_pricing(current_price, forecast)

    # Handle optional/nullable fields safely
    days_val = snapshot.get("days_until_departure")
    if days_val is None or (isinstance(days_val, float) and math.isnan(days_val)):
        # Was `else 7`. Not a harmless default: `analyze_demand` computes
        # `urgency = 1 / (days + 1)` and weights it 2.4 — the largest term in the
        # demand score — so a snapshot with no departure date was scored as though
        # the flight were a week out, urgency 0.125. On a snapshot that also
        # lacked seats and a demand score, that term was the *only* input, giving
        # a demand score of exactly 0.3 and the verdict "Demand pressure is low
        # enough to allow more waiting room": a booking horizon nobody supplied
        # became a reason to wait. Its two neighbours below already default to
        # None; this one is now consistent with them, and because the demand term
        # is dominated by it, the decision is refused rather than issued on a
        # substituted week.
        raise PredictionUnavailable(
            "Booking decision requires days_until_departure; the snapshot does "
            "not record one, and the demand term is dominated by it."
        )
    days_until_departure = int(days_val)

    seats_val = snapshot.get("seats_available")
    seats_available = int(seats_val) if seats_val is not None and not (isinstance(seats_val, float) and math.isnan(seats_val)) else None

    demand_val = snapshot.get("demand_score")
    demand_score = float(demand_val) if demand_val is not None and not (isinstance(demand_val, float) and math.isnan(demand_val)) else None

    demand = analyze_demand(
        days_until_departure,
        seats_available,
        demand_score,
    )
    risk = analyze_risk(forecast, current_price)

    buy_score = 0.0
    buy_score += max(0.0, pricing["score"]) * 0.44
    buy_score += demand["score"] * 0.36
    buy_score += risk["score"] * 0.20
    wait_score = max(0.0, -pricing["score"]) * 0.58 + (1.0 - demand["score"]) * 0.28

    decision = "BOOK NOW" if buy_score >= wait_score else "WAIT"
    margin = abs(buy_score - wait_score)

    reasons = [pricing["reason"], demand["reason"], risk["reason"]]
    if decision == "BOOK NOW":
        reasons.append("The combined agent score favors locking the fare before upward pressure compounds.")
    else:
        reasons.append("The combined agent score leaves enough room to monitor for a better fare.")

    return {
        "decision": decision,
        # Was `round(min(0.94, max(0.52, 0.56 + margin * 0.55)), 2)`.
        #
        # That is the margin between two hand-weighted scores, put through a
        # linear map and clamped into 0.52-0.94. Nothing about it was measured
        # against outcomes: no record exists of how often "BOOK NOW at 0.87" was
        # the right call, so the number could not be a frequency, and the floor of
        # 0.52 meant no decision was ever reported as less than half confident
        # however evenly the agents split. Published beside a fare, next to the
        # word confidence, it invites exactly the reading it cannot support.
        #
        # It is null until something measures decision outcomes. The quantity that
        # does exist — how far apart the two sides came out — is published under
        # its own name, along with the component scores it was computed from, so a
        # caller can see how close the call was without being told a probability.
        "confidence": None,
        "decision_margin": round(margin, 4),
        "component_scores": {
            "pricing": pricing["score"],
            "demand": demand["score"],
            "risk": risk["score"],
            "buy": round(buy_score, 4),
            "wait": round(wait_score, 4),
        },
        "reasons": reasons,
    }
