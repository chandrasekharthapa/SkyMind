import pytest
from backend.services.langsmith_tracer import langsmith_tracer, LangSmithTracer


def test_langsmith_tracer_initialization():
    """Verify LangSmithTracer initializes safely without throwing exceptions."""
    tracer = LangSmithTracer()
    assert hasattr(tracer, "enabled")
    assert hasattr(tracer, "project_name")


def test_token_estimation_and_cost():
    """Verify static token estimation and cost calculation methods."""
    text = "Find flights from Delhi to Mumbai on 2026-08-01"
    token_count = LangSmithTracer.estimate_tokens(text)
    assert token_count > 5

    cost = LangSmithTracer.calculate_cost(prompt_tokens=1000, completion_tokens=500)
    assert cost == 0.00115  # (1 * 0.0007) + (0.5 * 0.0009) = 0.00115


def test_fail_open_tracing_behavior():
    """Verify tracer methods execute cleanly when LangSmith is disabled/unconfigured."""
    run = langsmith_tracer.trace_request("sess-123", "test query", [])
    assert run is None or hasattr(run, "id")

    # Should not throw exception
    langsmith_tracer.trace_tool_call("search_flights", {"origin": "DEL"}, {"status": "success"}, 0.15)
