import pytest
from backend.services.intent_planner import IntentPlanner
from backend.services.execution_planner import ExecutionPlanner, ExecutionPlan, ExecutionDAG


def test_single_tool_execution_plan():
    """Verify single-tool execution plan generation for SEARCH_FLIGHTS."""
    intent_planner = IntentPlanner()
    intent_res = intent_planner.rule_based_plan("Find flights from Delhi to Mumbai on 2026-08-01")
    
    exec_planner = ExecutionPlanner()
    plan = exec_planner.build_dag_from_intent(intent_res)

    assert isinstance(plan, ExecutionPlan)
    assert plan.intent == "SEARCH_FLIGHTS"
    assert len(plan.dag.nodes) == 1
    assert plan.dag.nodes[0].tool_name == "search_flights"
    assert plan.parallelism_score == 1.0


def test_multi_tool_parallel_execution_plan():
    """Verify multi-tool parallel execution plan for PREDICT_FARE."""
    intent_planner = IntentPlanner()
    intent_res = intent_planner.rule_based_plan("Predict fare trends for Delhi to Bangalore tomorrow")
    
    exec_planner = ExecutionPlanner()
    plan = exec_planner.build_dag_from_intent(intent_res)

    assert plan.intent == "PREDICT_FARE"
    assert len(plan.dag.nodes) == 2
    tool_names = [n.tool_name for n in plan.dag.nodes]
    assert "predict_price" in tool_names
    assert "forecast_prices" in tool_names
    assert len(plan.dag.parallel_batches) == 1
    assert plan.parallelism_score == 2.0


def test_recommendations_execution_plan():
    """Verify execution plan for RECOMMEND_BEST intent."""
    intent_planner = IntentPlanner()
    intent_res = intent_planner.rule_based_plan("Recommend cheapest flight from Mumbai to Delhi")
    
    exec_planner = ExecutionPlanner()
    plan = exec_planner.build_dag_from_intent(intent_res)

    assert plan.intent == "RECOMMEND_BEST"
    assert len(plan.dag.nodes) == 2
    tool_names = [n.tool_name for n in plan.dag.nodes]
    assert "recommend_flights" in tool_names
    assert "predict_price" in tool_names


@pytest.mark.asyncio
async def test_shadow_execution_planner():
    """Verify shadow execution planner runs asynchronously without error."""
    intent_planner = IntentPlanner()
    intent_res = intent_planner.rule_based_plan("Search flights")
    
    exec_planner = ExecutionPlanner()
    plan = await exec_planner.plan_shadow(intent_res)

    assert isinstance(plan, ExecutionPlan)
    assert plan.planning_latency_seconds >= 0.0
    assert len(plan.dag.nodes) >= 1
