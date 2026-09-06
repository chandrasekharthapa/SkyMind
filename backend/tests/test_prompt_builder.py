import pytest
from backend.services.prompt_builder import (
    ContextBuilder,
    CanonicalContext,
    UserPreferences,
    GenerationSettings,
    DEFAULT_SYSTEM_INSTRUCTIONS,
    DEFAULT_BUSINESS_POLICIES
)
from backend.services.intent_planner import IntentPlanner
from backend.services.evidence_builder import EvidenceBuilder


def test_canonical_context_empty_conversation():
    """Verify context construction for empty conversation."""
    builder = ContextBuilder()
    ctx = builder.build_context("sess_empty", [])
    
    assert isinstance(ctx, CanonicalContext)
    assert ctx.session_id == "sess_empty"
    assert len(ctx.formatted_history) == 0
    assert ctx.estimated_token_count > 10
    assert DEFAULT_BUSINESS_POLICIES[0] in ctx.full_prompt_text


def test_canonical_context_history_truncation():
    """Verify conversation history is deterministically truncated to last 10 turns."""
    builder = ContextBuilder()
    long_history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"} for i in range(25)]
    
    ctx = builder.build_context("sess_long", long_history)
    assert len(ctx.formatted_history) == 10
    assert ctx.formatted_history[0]["content"] == "Message 15"
    assert ctx.formatted_history[-1]["content"] == "Message 24"


def test_canonical_context_policy_and_preferences_injection():
    """Verify user preferences and business policies are deterministically injected."""
    builder = ContextBuilder()
    prefs = UserPreferences(preferred_airline="6E", home_airport="DEL", cabin_class="BUSINESS")
    
    ctx = builder.build_context("sess_prefs", [], preferences=prefs)
    assert "[USER PREFERENCES]" in ctx.full_prompt_text
    assert "Preferred Airline: 6E" in ctx.full_prompt_text
    assert "Home Airport: DEL" in ctx.full_prompt_text
    assert "Cabin: BUSINESS" in ctx.full_prompt_text


def test_canonical_context_with_evidence_and_planner():
    """Verify evidence package and planner summary injection."""
    intent_planner = IntentPlanner()
    intent_plan = intent_planner.rule_based_plan("Find flights from Delhi to Mumbai tomorrow")

    evidence_builder = EvidenceBuilder()
    mock_payloads = [{
        "_tool_name": "search_flights",
        "status": "success",
        "flights": [{"flight_number": "6E101", "primary_airline": "6E", "price": 4500.0}]
    }]
    evidence_pkg = evidence_builder.build_package("sess_ev", mock_payloads)

    builder = ContextBuilder()
    ctx = builder.build_context("sess_full", [], planner_output=intent_plan, evidence_package=evidence_pkg)

    assert "[PLANNER CONTEXT]" in ctx.full_prompt_text
    assert "Classified Intent: SEARCH_FLIGHTS" in ctx.full_prompt_text
    assert "[EVIDENCE PACKAGE (1 Verified Items)]" in ctx.full_prompt_text
    assert "6E101" in ctx.full_prompt_text


@pytest.mark.asyncio
async def test_shadow_context_builder():
    """Verify non-blocking shadow context builder execution."""
    builder = ContextBuilder()
    ctx = await builder.build_shadow("sess_async", [{"role": "user", "content": "Hello"}])
    
    assert isinstance(ctx, CanonicalContext)
    assert ctx.construction_latency_seconds >= 0.0
    assert ctx.estimated_token_count > 0
