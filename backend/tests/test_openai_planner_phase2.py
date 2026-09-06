"""Unit tests for Phase 2.0 Planner-Informed Prompt Construction."""

import pytest
from backend.services.openai_planner import PlanningResult
from backend.services.chatbot_service import format_planner_prompt_section

def test_format_planner_prompt_section_none():
    """Verify None input returns empty string for backward compatibility."""
    assert format_planner_prompt_section(None) == ""

def test_format_planner_prompt_section_valid():
    """Verify formatted advisory section output."""
    res = PlanningResult(
        intent="SEARCH_FLIGHTS",
        entities={"origin": "DEL", "destination": "BOM", "departure_date": "2026-08-15"},
        required_tools=["search_flights", "predict_price"],
        execution_order=["search_flights", "predict_price"],
        parallel_execution=True,
        requires_clarification=False,
        confidence=0.97,
        planner_source="openai"
    )

    formatted = format_planner_prompt_section(res)
    
    assert "[ADVISORY AI PLANNING CONTEXT]" in formatted
    assert "Intent:\nSEARCH_FLIGHTS" in formatted
    assert "Confidence:\n0.97" in formatted
    assert "Planner Source:\nopenai" in formatted
    assert "Origin: DEL" in formatted
    assert "Destination: BOM" in formatted
    assert "- search_flights" in formatted
    assert "- predict_price" in formatted
    assert "Parallel Execution: true" in formatted

def test_format_planner_prompt_section_with_clarification():
    """Verify advisory note appended when requires_clarification is True."""
    res = PlanningResult(
        intent="SEARCH_FLIGHTS",
        entities={},
        required_tools=[],
        execution_order=[],
        parallel_execution=True,
        requires_clarification=True,
        confidence=0.60,
        planner_source="rule_based"
    )

    formatted = format_planner_prompt_section(res)
    assert "Requires Clarification: true" in formatted
    assert "Advisory Note: Planner believes additional user clarification may be required" in formatted
