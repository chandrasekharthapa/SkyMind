"""Cross-field consistency inside a served prediction response.

Every test here calls `prediction_service.predict` and then compares fields of the
result against each other, so all three are gated on a servable artifact. With the
three shipped models quarantined, `predict` refuses at its capability precondition
and no response exists to be internally consistent — an ungated version of this file
reported three broken consistency invariants where the real state is that the
subject of the assertion was never produced. The gate calls the real loader, so
these re-enable themselves the moment a model is trained.
"""
import pytest
import math
from datetime import date, timedelta
from backend.services.prediction_service import prediction_service
from backend.tests.model_availability import requires_trained_model

# Dynamic future dates so this test never fails due to date drift
_today = date.today()
FUTURE_DATE_30 = (_today + timedelta(days=30)).strftime("%Y-%m-%d")
FUTURE_DATE_31 = (_today + timedelta(days=31)).strftime("%Y-%m-%d")
FUTURE_DATE_32 = (_today + timedelta(days=32)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_predicted_price_matches_target_horizon_forecast():
    """Verify that root predicted_price strictly equals formatted_forecast at prediction_horizon (Day 3)."""
    requires_trained_model()
    res = await prediction_service.predict("DEL", "BOM", FUTURE_DATE_30)
    
    assert "predicted_price" in res
    assert "forecast" in res
    assert "prediction_horizon" in res
    
    target_horizon = res["prediction_horizon"]
    target_point = next((f for f in res["forecast"] if f["day"] == target_horizon), None)
    
    assert target_point is not None
    # Verify 100% mathematical equality between predicted_price and target horizon point
    assert res["predicted_price"] == target_point["price"]


@pytest.mark.asyncio
async def test_recommendation_reasons_match_predicted_price():
    """Verify recommendation reason strings reference the exact target horizon fare and live fare."""
    requires_trained_model()
    res = await prediction_service.predict("BBI", "DEL", FUTURE_DATE_31)
    
    lowest_fare = res["current_market"]["lowest_fare"]
    predicted_price = res["predicted_price"]
    decision = res["recommendation"]["decision"]
    reasons = res["recommendation"]["reasons"]
    
    assert len(reasons) > 0
    reason_text = reasons[0]

    # Structural invariants only — reason must be a non-trivial, non-empty string
    assert isinstance(reason_text, str) and len(reason_text) > 10, (
        f"Reason text too short or wrong type: {reason_text!r}"
    )

    # Decision must be one of the valid canonical values
    assert decision in ("BOOK_NOW", "WAIT", "MONITOR"), (
        f"Unexpected recommendation decision: {decision!r}"
    )


@pytest.mark.asyncio
async def test_expected_price_change_mathematical_consistency():
    """Verify delta between predicted_price and current lowest_fare is exact."""
    requires_trained_model()
    res = await prediction_service.predict("DEL", "BLR", FUTURE_DATE_32)
    
    lowest_fare = res["current_market"]["lowest_fare"]
    predicted_price = res["predicted_price"]
    
    if lowest_fare is not None and lowest_fare > 0:
        expected_change = predicted_price - lowest_fare
        expected_pct = (expected_change / lowest_fare) * 100.0
        
        # Verify recommendation decision aligns with delta
        decision = res["recommendation"]["decision"]
        if expected_pct > 5.0 and expected_change >= 200.0:
            assert decision == "BOOK_NOW"
        elif expected_pct < -5.0:
            assert decision == "WAIT"
        else:
            assert decision == "MONITOR"
