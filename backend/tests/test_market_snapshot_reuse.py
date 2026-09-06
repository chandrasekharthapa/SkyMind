import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.domain.market_snapshot import MarketSnapshot
from backend.services.agents.decision_agent import make_decision
from backend.utils.exceptions import PredictionUnavailable

def test_market_snapshot_reused_by_recommendation():
    """Verify MarketSnapshot is compatible and reusable by the Recommendation decision logic."""
    snapshot = MarketSnapshot(
        lowest_fare=5000.0,
        highest_fare=10000.0,
        average_fare=7500.0,
        median_fare=7500.0,
        fare_spread=5000.0,
        price_std_dev=2500.0,
        total_live_flights=5,
        direct_flight_count=3,
        connecting_flight_count=2,
        retrieval_timestamp="2026-07-19T12:00:00",
        provider="Test Provider",
        search_duration=0.1,
        search_success=True
    )
    
    forecast = [
        {"day": 1, "date": "2026-07-27", "price": 4900.0, "lower": 4500.0, "upper": 5200.0},
        {"day": 2, "date": "2026-07-28", "price": 4800.0, "lower": 4400.0, "upper": 5100.0}
    ]
    
    # We pass mapped details from MarketSnapshot to make_decision
    snapshot_ctx = {
        "origin": "DEL",
        "destination": "BOM",
        "airline": "6E",
        "departure_date": "2026-07-26",
        "seats_available": 15,
        "current_price": snapshot.lowest_fare,
        "days_until_departure": 7,
        "demand_score": 0.5,
        "seasonality_factor": 1.0
    }
    
    decision = make_decision(snapshot_ctx, forecast)
    assert decision["decision"] in ("BOOK NOW", "WAIT")

    # Was `assert decision["confidence"] >= 0.0`. That could not fail: the value
    # was clamped into 0.52-0.94, so the assertion held for every input and
    # ratified a confidence figure nothing had measured.
    assert decision["confidence"] is None

    # What is actually computed is published under its own name.
    assert decision["decision_margin"] >= 0.0
    comp = decision["component_scores"]
    assert set(comp) == {"pricing", "demand", "risk", "buy", "wait"}
    assert decision["decision_margin"] == pytest.approx(abs(comp["buy"] - comp["wait"]), abs=1e-4)
    assert (decision["decision"] == "BOOK NOW") == (comp["buy"] >= comp["wait"])
    assert len(decision["reasons"]) == 4


def test_decision_refuses_without_a_booking_horizon():
    """No departure horizon means no decision, not a decision computed from 7 days."""
    forecast = [
        {"day": 1, "date": "2026-07-27", "price": 4900.0, "lower": 4500.0, "upper": 5200.0},
    ]
    ctx = {"current_price": 5000.0, "seats_available": 15, "demand_score": 0.5}

    with pytest.raises(PredictionUnavailable) as excinfo:
        make_decision(ctx, forecast)
    assert "days_until_departure" in str(excinfo.value)

    # An explicit NaN is the same absence, not a number.
    with pytest.raises(PredictionUnavailable):
        make_decision({**ctx, "days_until_departure": float("nan")}, forecast)

    # And a horizon that is present is still served.
    served = make_decision({**ctx, "days_until_departure": 7}, forecast)
    assert served["decision"] in ("BOOK NOW", "WAIT")
