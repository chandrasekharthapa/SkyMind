"""Unit tests for Phase 1 OpenAI Planning Agent Integration."""

import pytest
import asyncio
from backend.services.openai_planner import PlanningResult, openai_planner
from backend.services.intent_planner import intent_planner

@pytest.mark.asyncio
async def test_openai_planner_schema():
    """Verify PlanningResult Pydantic schema instantiation."""
    res = PlanningResult(
        intent="SEARCH_FLIGHTS",
        entities={"origin": "DEL", "destination": "BOM"},
        required_tools=["search_flights"],
        execution_order=["search_flights"],
        parallel_execution=True,
        requires_clarification=False,
        confidence=0.98,
        reasoning="User requested flight search"
    )
    assert res.intent == "SEARCH_FLIGHTS"
    assert res.required_tools == ["search_flights"]
    assert res.fallback_used is False

@pytest.mark.asyncio
async def test_intent_planner_hybrid_fallback():
    """Verify Hybrid Intent Planner activates rule-based fallback when OpenAI key is missing."""
    res = await intent_planner.plan("Find flights from Delhi to Mumbai tomorrow", {"origin": "DEL", "destination": "BOM"})
    assert isinstance(res, PlanningResult)
    assert res.intent == "SEARCH_FLIGHTS"
    assert res.fallback_used is True
    assert res.provider_used == "rule_based"
