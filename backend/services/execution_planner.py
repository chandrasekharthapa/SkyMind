"""SkyMind Execution Planner Service (Shadow Mode).

Consumes IntentClassification outputs to build deterministic ExecutionDAGs,
detailing required tools, execution order, dependency graphs, retry policies,
timeout constraints, and parallel execution batches without executing tools or workflows.
"""

import os
import time
import logging
import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from opentelemetry import metrics

from backend.services.intent_planner import IntentClassification
from backend.services.langsmith_tracer import langsmith_tracer

logger = logging.getLogger(__name__)

# OpenTelemetry Metrics
meter = metrics.get_meter("skymind.execution_planner")
execution_planner_latency_hist = meter.create_histogram(name="chat_execution_planner_latency_seconds", description="Execution planner duration")
dag_nodes_hist = meter.create_histogram(name="chat_execution_dag_nodes_total", description="Execution DAG node count")
parallelism_score_hist = meter.create_histogram(name="chat_execution_parallelism_score", description="DAG parallelism ratio")
execution_planner_failures_counter = meter.create_counter(name="chat_execution_planner_failures_total", description="Execution planner failures")


class ExecutionPolicy(BaseModel):
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0
    timeout_seconds: float = 5.0
    allow_parallel: bool = True


class ExecutionNode(BaseModel):
    id: str = Field(description="Unique node identifier e.g. step_1")
    tool_name: str
    arguments: Dict[str, Any]
    policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    estimated_duration_seconds: float = 0.5


class ExecutionEdge(BaseModel):
    from_node_id: str
    to_node_id: str


class ExecutionDAG(BaseModel):
    nodes: List[ExecutionNode] = Field(default_factory=list)
    edges: List[ExecutionEdge] = Field(default_factory=list)
    parallel_batches: List[List[str]] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    intent: str
    dag: ExecutionDAG = Field(default_factory=ExecutionDAG)
    total_estimated_timeout_seconds: float = 5.0
    dependency_count: int = 0
    parallelism_score: float = 1.0
    planning_latency_seconds: float = 0.0


class ExecutionPlanner:
    """Deterministic Execution Planner."""

    def build_dag_from_intent(self, intent_plan: IntentClassification) -> ExecutionPlan:
        """Constructs deterministic execution DAG from IntentClassification schema."""
        start_time = time.time()
        intent = intent_plan.intent
        norm = intent_plan.normalized_values

        nodes = []
        edges = []
        batches = []

        args_basic = {
            "origin": norm.origin_iata or "DEL",
            "destination": norm.destination_iata or "BOM",
            "departure_date": norm.departure_date_iso or "2026-08-01",
        }

        if intent in ["SEARCH_FLIGHTS", "GENERAL_INQUIRY"]:
            node1 = ExecutionNode(id="step_1", tool_name="search_flights", arguments=args_basic)
            nodes.append(node1)
            batches.append(["step_1"])

        elif intent == "PREDICT_FARE":
            node1 = ExecutionNode(id="step_1", tool_name="predict_price", arguments=args_basic)
            node2 = ExecutionNode(id="step_2", tool_name="forecast_prices", arguments=args_basic)
            nodes.extend([node1, node2])
            batches.append(["step_1", "step_2"])  # Parallel batch

        elif intent == "RECOMMEND_BEST":
            node1 = ExecutionNode(id="step_1", tool_name="recommend_flights", arguments=args_basic)
            node2 = ExecutionNode(id="step_2", tool_name="predict_price", arguments=args_basic)
            nodes.extend([node1, node2])
            batches.append(["step_1", "step_2"])  # Parallel batch

        elif intent == "COMPARE_FLIGHTS":
            node1 = ExecutionNode(id="step_1", tool_name="compare_flights", arguments=args_basic)
            node2 = ExecutionNode(id="step_2", tool_name="historical_prices", arguments=args_basic)
            nodes.extend([node1, node2])
            batches.append(["step_1", "step_2"])  # Parallel batch

        elif intent == "HISTORICAL_PRICE":
            node1 = ExecutionNode(id="step_1", tool_name="historical_prices", arguments=args_basic)
            nodes.append(node1)
            batches.append(["step_1"])

        elif intent == "ROUTE_INFO":
            node1 = ExecutionNode(id="step_1", tool_name="route_information", arguments={"origin": norm.origin_iata or "DEL", "destination": norm.destination_iata or "BOM"})
            nodes.append(node1)
            batches.append(["step_1"])

        elif intent == "AIRPORT_INFO":
            node1 = ExecutionNode(id="step_1", tool_name="airport_information", arguments={"query": norm.destination_iata or norm.origin_iata or "DEL"})
            nodes.append(node1)
            batches.append(["step_1"])

        else:
            # Default single flight search
            node1 = ExecutionNode(id="step_1", tool_name="search_flights", arguments=args_basic)
            nodes.append(node1)
            batches.append(["step_1"])

        dep_count = len(edges)
        num_batches = max(len(batches), 1)
        para_score = round(len(nodes) / float(num_batches), 2)
        total_timeout = sum(n.policy.timeout_seconds for n in nodes)

        duration = time.time() - start_time

        dag = ExecutionDAG(nodes=nodes, edges=edges, parallel_batches=batches)

        plan = ExecutionPlan(
            intent=intent,
            dag=dag,
            total_estimated_timeout_seconds=total_timeout,
            dependency_count=dep_count,
            parallelism_score=para_score,
            planning_latency_seconds=duration
        )

        return plan

    async def plan_shadow(self, intent_plan: IntentClassification, timeout_seconds: float = 2.0) -> ExecutionPlan:
        """Executes execution planning in non-blocking shadow mode."""
        start_time = time.time()
        try:
            plan = await asyncio.wait_for(
                asyncio.to_thread(self.build_dag_from_intent, intent_plan),
                timeout=timeout_seconds
            )
            duration = time.time() - start_time

            # Record Telemetry
            execution_planner_latency_hist.record(duration)
            dag_nodes_hist.record(len(plan.dag.nodes))
            parallelism_score_hist.record(plan.parallelism_score)

            logger.info(
                f"[ShadowExecutionPlanner] Intent: {plan.intent} | "
                f"Nodes: {len(plan.dag.nodes)} | "
                f"Batches: {len(plan.dag.parallel_batches)} | "
                f"ParallelismScore: {plan.parallelism_score} | "
                f"Duration: {duration:.4f}s"
            )

            # LangSmith Shadow Trace
            langsmith_tracer.trace_tool_call(
                tool_name="shadow_execution_planner",
                args={"intent": intent_plan.intent},
                result=plan.model_dump(),
                duration_seconds=duration
            )

            return plan

        except Exception as e:
            execution_planner_failures_counter.add(1)
            logger.warning(f"[ShadowExecutionPlanner] Execution planning error (fail-safe): {e}")
            return ExecutionPlan(
                intent=intent_plan.intent,
                dag=ExecutionDAG(),
                planning_latency_seconds=time.time() - start_time
            )


execution_planner = ExecutionPlanner()
