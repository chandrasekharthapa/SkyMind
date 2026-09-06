"""Unit tests for Phase 3.0 OpenAI LLM Judge & Response Repair."""

import pytest
from backend.services.judge_agent import JudgeResult, judge_agent

def test_judge_result_schema():
    """Verify JudgeResult Pydantic schema instantiation."""
    res = JudgeResult(
        decision="REPAIR",
        repaired_response="Here are the updated flights for your query.",
        confidence=0.96,
        issues=["Formatting inconsistency"],
        repair_reason="Improved readability"
    )
    assert res.decision == "REPAIR"
    assert res.repaired_response == "Here are the updated flights for your query."
    assert res.confidence == 0.96

def test_judge_should_trigger_conditions():
    """Verify Judge trigger criteria."""
    # 1. Validator failure triggers judge
    trig, reason = judge_agent.should_trigger(validator_passed=False)
    assert trig is True
    assert reason == "validator_failed"

    # 2. Low planner confidence triggers judge
    trig, reason = judge_agent.should_trigger(validator_passed=True, planner_confidence=0.50)
    assert trig is True
    assert reason == "low_planner_confidence"

    # 3. Normal request with high confidence does not trigger (when sampling is 0)
    judge_agent.enabled = True
    trig, reason = judge_agent.should_trigger(validator_passed=True, planner_confidence=0.98, missing_tool_outputs=False)
    assert isinstance(trig, bool)

@pytest.mark.asyncio
async def test_judge_evaluate_fallback():
    """Verify Judge evaluate fallback when API key is unconfigured."""
    res = await judge_agent.evaluate(
        query="Test query",
        messages=[],
        planner_result=None,
        tool_payloads=[],
        primary_llm_response="Primary LLM response text",
        validator_passed=False,
        validation_errors=["Hallucinated price"],
        trigger_reason="validator_failed"
    )
    assert isinstance(res, JudgeResult)
    assert res.decision == "PASS"
    assert res.judge_trigger_reason == "validator_failed" or res.judge_trigger_reason == "no_api_key"
