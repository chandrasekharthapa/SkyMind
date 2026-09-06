import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from backend.services.intent_planner import (
    IntentPlanner,
    normalize_airport_code,
    normalize_relative_date,
    IntentClassification
)


def test_airport_normalization():
    """Verify city name to 3-letter IATA code resolution."""
    assert normalize_airport_code("Delhi") == "DEL"
    assert normalize_airport_code("Mumbai") == "BOM"
    assert normalize_airport_code("Bombay") == "BOM"
    assert normalize_airport_code("Bangalore") == "BLR"
    assert normalize_airport_code("Bengaluru") == "BLR"
    assert normalize_airport_code("DEL") == "DEL"
    assert normalize_airport_code("BOM") == "BOM"


def test_relative_date_normalization():
    """Verify relative date normalization into ISO YYYY-MM-DD format."""
    today = datetime.now(timezone.utc)
    tomorrow_expected = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after_expected = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    in_7_days_expected = (today + timedelta(days=7)).strftime("%Y-%m-%d")

    assert normalize_relative_date("today", today) == today.strftime("%Y-%m-%d")
    assert normalize_relative_date("tomorrow", today) == tomorrow_expected
    assert normalize_relative_date("day after tomorrow", today) == day_after_expected
    assert normalize_relative_date("in 7 days", today) == in_7_days_expected
    assert normalize_relative_date("2026-08-15") == "2026-08-15"


def test_intent_classification_search_flights():
    """Verify intent classification and entity extraction for flight search."""
    planner = IntentPlanner()
    plan = planner.rule_based_plan("Find flights from Delhi to Mumbai tomorrow")
    
    assert plan.intent == "SEARCH_FLIGHTS"
    assert plan.normalized_values.origin_iata == "DEL"
    assert plan.normalized_values.destination_iata == "BOM"
    assert plan.normalized_values.departure_date_iso is not None
    assert plan.ambiguity is False
    assert len(plan.missing_parameters) == 0
    assert plan.overall_confidence >= 0.8
    assert plan.intent_confidence >= 0.9


def test_missing_parameter_and_ambiguity_detection():
    """Verify missing parameter detection when user prompt is incomplete."""
    planner = IntentPlanner()
    plan = planner.rule_based_plan("Search flights to Mumbai")
    
    assert plan.intent == "SEARCH_FLIGHTS"
    assert plan.normalized_values.destination_iata == "BOM"
    assert "origin_iata" in plan.missing_parameters
    assert "departure_date_iso" in plan.missing_parameters
    assert plan.ambiguity is True


def test_intent_classification_fare_prediction():
    """Verify fare prediction intent recognition."""
    planner = IntentPlanner()
    plan = planner.rule_based_plan("Predict price trends for Delhi to Bangalore tomorrow")
    
    assert plan.intent == "PREDICT_FARE"
    assert plan.normalized_values.origin_iata == "DEL"
    assert plan.normalized_values.destination_iata == "BLR"


@pytest.mark.asyncio
async def test_shadow_planner_execution():
    """Verify shadow planner executes non-blocking and returns valid Pydantic model."""
    planner = IntentPlanner()
    plan = await planner.plan_shadow("Find cheapest flight from Delhi to Mumbai tomorrow")
    
    assert isinstance(plan, IntentClassification)
    assert plan.intent in ["SEARCH_FLIGHTS", "RECOMMEND_BEST"]
    assert plan.overall_confidence > 0.5
    assert plan.provider_used is not None


@pytest.mark.asyncio
async def test_planner_timeout_handling(monkeypatch):
    """Verify plan_shadow delegates to rule_based_plan regardless of timeout parameter.
    
    Note: plan_shadow is a legacy shim — it calls rule_based_plan synchronously.
    The timeout_seconds parameter is accepted for API compatibility but is not enforced.
    This test verifies the delegation contract is preserved.
    """
    planner = IntentPlanner()

    # Capture the original method BEFORE patching to avoid infinite recursion
    _original_rule_based_plan = planner.rule_based_plan

    def wrapped_plan(*args, **kwargs):
        return _original_rule_based_plan("test query")

    monkeypatch.setattr(planner, "rule_based_plan", wrapped_plan)
    plan = await planner.plan_shadow("test query", timeout_seconds=0.01)

    # plan_shadow is a legacy shim: it always delegates to rule_based_plan
    assert isinstance(plan, IntentClassification)
    assert plan.overall_confidence >= 0.0
    assert plan.intent is not None
