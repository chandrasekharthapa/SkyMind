"""SkyMind LangGraph Agent State Machine Orchestrator.

Wraps existing domain services (Firewall, Governance, IntentPlanner, ExecutionPlanner,
ToolExecutor, EvidenceBuilder, ContextBuilder, Generator, and Validator) inside a compiled
LangGraph StateGraph supporting checkpointing, state recovery, and conditional branching.
"""

import os
import json
import time
import logging
import asyncio
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from pydantic import BaseModel
from opentelemetry import metrics

try:
    from langgraph.graph import StateGraph, END, START
    from langgraph.checkpoint.memory import MemorySaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    END = "__end__"
    START = "__start__"
    
    class MemorySaver:
        def __init__(self):
            self.storage = {}
        def put(self, config, checkpoint):
            thread_id = config.get("configurable", {}).get("thread_id", "default")
            self.storage[thread_id] = checkpoint
        def get(self, config):
            thread_id = config.get("configurable", {}).get("thread_id", "default")
            return self.storage.get(thread_id)

from backend.firewall import FirewallConfig, PolicyPlatform, PolicyLoader
from backend.governance.classifier import classify_message
from backend.governance.engine import GovernancePolicyLoader
from backend.governance.models import GovernanceActionEnum

from backend.services.intent_planner import intent_planner, IntentClassification
from backend.services.execution_planner import execution_planner, ExecutionPlan
from backend.services.chatbot_tools import execute_chatbot_tool
from backend.services.evidence_builder import evidence_builder, EvidencePackage
from backend.services.prompt_builder import context_builder, CanonicalContext
from backend.services.chat_response_validator import ChatResponseValidator
from backend.services.langsmith_tracer import langsmith_tracer

logger = logging.getLogger(__name__)

# OpenTelemetry Metrics
meter = metrics.get_meter("skymind.agent_graph")
graph_duration_hist = meter.create_histogram(name="chat_graph_duration_seconds", description="LangGraph execution duration")
graph_node_latency_hist = meter.create_histogram(name="chat_graph_node_latency_seconds", description="Graph node latency")
checkpoint_count_counter = meter.create_counter(name="chat_graph_checkpoints_total", description="Checkpoint count")
graph_failures_counter = meter.create_counter(name="chat_graph_failures_total", description="Graph failures")

firewall_config = FirewallConfig()
# See the note in `routers/chat.py`: this was the second copy of
# `PolicyLoader(file_path="policy.yaml")`, a working-directory-relative path that
# resolved to nothing and left the graph running on an empty, allow-everything
# policy. `PolicyLoader` now resolves `backend/policy.yaml` from its own `__file__`.
firewall_policy_loader = PolicyLoader()
policy_platform = PolicyPlatform(config=firewall_config, policy_loader=firewall_policy_loader)
governance_loader = GovernancePolicyLoader()


class GraphAgentState(TypedDict):
    session_id: str
    messages: List[Dict[str, Any]]
    latest_query: str
    search_context: Dict[str, Any]
    is_safe: bool
    firewall_violation: Optional[str]
    domain: str
    governance_ack: Optional[str]
    intent_classification: Optional[Dict[str, Any]]
    execution_plan: Optional[Dict[str, Any]]
    tool_payloads: List[Dict[str, Any]]
    evidence_package: Optional[Dict[str, Any]]
    canonical_context: Optional[Dict[str, Any]]
    generated_text: str
    validation_passed: bool
    retry_count: int
    error: Optional[str]


# ── Node Implementations ──────────────────────────────────────────────

async def node_firewall(state: GraphAgentState) -> Dict[str, Any]:
    """Node 1: Evaluates safety firewall."""
    t0 = time.time()
    query = state["latest_query"]
    is_safe = True
    violation = None

    try:
        context = await policy_platform.evaluate_messages([{"role": "user", "content": query}])
        if not context.decision.is_safe:
            is_safe = False
            violation = context.decision.violations[0] if context.decision.violations else "unknown"
    except Exception as e:
        logger.warning(f"[GraphNode:firewall] Firewall check fail-open: {e}")

    graph_node_latency_hist.record(time.time() - t0, {"node": "firewall"})
    return {"is_safe": is_safe, "firewall_violation": violation}


def node_governance(state: GraphAgentState) -> Dict[str, Any]:
    """Node 2: Evaluates domain governance rules."""
    t0 = time.time()
    query = state["latest_query"]
    domain = "AVIATION"
    ack = None

    try:
        classification = classify_message(query)
        gov_decision = governance_loader.get_action(classification.domain)
        domain = classification.domain.value

        if gov_decision.action != GovernanceActionEnum.ALLOW:
            ack = gov_decision.acknowledgement or "I'm designed to help with aviation and travel."
    except Exception as e:
        logger.warning(f"[GraphNode:governance] Governance check fail-open: {e}")

    graph_node_latency_hist.record(time.time() - t0, {"node": "governance"})
    return {"domain": domain, "governance_ack": ack}


def node_intent_planner(state: GraphAgentState) -> Dict[str, Any]:
    """Node 3: Executes structured intent planner."""
    t0 = time.time()
    plan = intent_planner.rule_based_plan(state["latest_query"], state.get("search_context"))
    graph_node_latency_hist.record(time.time() - t0, {"node": "intent_planner"})
    return {"intent_classification": plan.model_dump()}


def node_execution_planner(state: GraphAgentState) -> Dict[str, Any]:
    """Node 4: Executes deterministic execution planner."""
    t0 = time.time()
    intent_data = state.get("intent_classification") or {}
    intent_obj = IntentClassification.model_validate(intent_data) if intent_data else intent_planner.rule_based_plan(state["latest_query"])
    exec_plan = execution_planner.build_dag_from_intent(intent_obj)
    graph_node_latency_hist.record(time.time() - t0, {"node": "execution_planner"})
    return {"execution_plan": exec_plan.model_dump()}


async def node_tool_executor(state: GraphAgentState) -> Dict[str, Any]:
    """Node 5: Executes deterministic tool DAG concurrently."""
    t0 = time.time()
    exec_plan_data = state.get("execution_plan") or {}
    dag_nodes = exec_plan_data.get("dag", {}).get("nodes", [])

    tasks = []
    tool_meta = []
    for node in dag_nodes:
        name = node.get("tool_name")
        args = node.get("arguments", {})
        tool_meta.append(name)
        tasks.append(execute_chatbot_tool(name, args))

    results = []
    if tasks:
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        for idx, res in enumerate(raw_results):
            if isinstance(res, Exception):
                res = {"status": "error", "message": str(res)}
            res["_tool_name"] = tool_meta[idx]
            results.append(res)

    graph_node_latency_hist.record(time.time() - t0, {"node": "tool_executor"})
    return {"tool_payloads": results}


def node_evidence_builder(state: GraphAgentState) -> Dict[str, Any]:
    """Node 6: Normalizes tool outputs into canonical EvidencePackage."""
    t0 = time.time()
    pkg = evidence_builder.build_package(state["session_id"], state.get("tool_payloads", []))
    graph_node_latency_hist.record(time.time() - t0, {"node": "evidence_builder"})
    return {"evidence_package": pkg.model_dump()}


def node_context_builder(state: GraphAgentState) -> Dict[str, Any]:
    """Node 7: Assembles canonical prompt context."""
    t0 = time.time()
    intent_obj = IntentClassification.model_validate(state["intent_classification"]) if state.get("intent_classification") else None
    ev_pkg = EvidencePackage.model_validate(state["evidence_package"]) if state.get("evidence_package") else None

    ctx = context_builder.build_context(
        session_id=state["session_id"],
        messages=state["messages"],
        planner_output=intent_obj,
        evidence_package=ev_pkg
    )
    graph_node_latency_hist.record(time.time() - t0, {"node": "context_builder"})
    return {"canonical_context": ctx.model_dump()}


async def node_generator(state: GraphAgentState) -> Dict[str, Any]:
    """Node 8: Synthesizes output response."""
    t0 = time.time()
    tool_payloads = state.get("tool_payloads", [])
    
    if not tool_payloads:
        text = "Live pricing data isn't available for this route right now. Try again shortly."
    else:
        text = "Here are the flight intelligence insights for your request."

    graph_node_latency_hist.record(time.time() - t0, {"node": "generator"})
    return {"generated_text": text}


def node_validator(state: GraphAgentState) -> Dict[str, Any]:
    """Node 9: Validates response for hallucinations."""
    t0 = time.time()
    text = state.get("generated_text", "")
    payloads = state.get("tool_payloads", [])

    is_valid = ChatResponseValidator.validate_llm_response(text, payloads)
    retry_cnt = state.get("retry_count", 0) + (0 if is_valid else 1)

    graph_node_latency_hist.record(time.time() - t0, {"node": "validator"})
    return {"validation_passed": is_valid, "retry_count": retry_cnt}


# ── Conditional Routing Functions ────────────────────────────────────

def route_firewall(state: GraphAgentState) -> str:
    if not state["is_safe"]:
        return END
    return "governance"


def route_governance(state: GraphAgentState) -> str:
    if state["domain"].upper() not in ["AVIATION", "GREETING"]:
        return END
    return "intent_planner"


def route_validator(state: GraphAgentState) -> str:
    if state["validation_passed"] or state.get("retry_count", 0) >= 2:
        return END
    return "generator"


# ── Graph Construction & Fallback App Class ───────────────────────────

class FallbackStateGraphApp:
    """Lightweight fallback state machine app when langgraph is compiling."""

    def __init__(self, checkpointer: MemorySaver):
        self.checkpointer = checkpointer

    async def ainvoke(self, input_state: GraphAgentState, config: Optional[Dict[str, Any]] = None) -> GraphAgentState:
        state = dict(input_state)
        thread_id = config.get("configurable", {}).get("thread_id", "default") if config else "default"

        # Node 1: Firewall
        out = await node_firewall(state)
        state.update(out)
        if route_firewall(state) == END:
            self._save_checkpoint(thread_id, state)
            return state

        # Node 2: Governance
        out = node_governance(state)
        state.update(out)
        if route_governance(state) == END:
            self._save_checkpoint(thread_id, state)
            return state

        # Node 3: Intent Planner
        out = node_intent_planner(state)
        state.update(out)

        # Node 4: Execution Planner
        out = node_execution_planner(state)
        state.update(out)

        # Node 5: Tool Executor
        out = await node_tool_executor(state)
        state.update(out)

        # Node 6: Evidence Builder
        out = node_evidence_builder(state)
        state.update(out)

        # Node 7: Context Builder
        out = node_context_builder(state)
        state.update(out)

        # Node 8: Generator
        out = await node_generator(state)
        state.update(out)

        # Node 9: Validator
        out = node_validator(state)
        state.update(out)

        self._save_checkpoint(thread_id, state)
        return state

    def get_state(self, config: Dict[str, Any]) -> Any:
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint = self.checkpointer.get(config)
        if checkpoint:
            class StateContainer:
                def __init__(self, values):
                    self.values = values
            return StateContainer(checkpoint)
        return None

    def _save_checkpoint(self, thread_id: str, state: GraphAgentState):
        checkpoint_count_counter.add(1)
        self.checkpointer.put({"configurable": {"thread_id": thread_id}}, state)


def build_sky_agent_graph(checkpointer: Optional[Any] = None) -> Any:
    """Builds and compiles the SkyMind Agent Orchestration StateGraph."""
    mem_checkpointer = checkpointer or MemorySaver()

    if LANGGRAPH_AVAILABLE:
        try:
            workflow = StateGraph(GraphAgentState)

            workflow.add_node("firewall", node_firewall)
            workflow.add_node("governance", node_governance)
            workflow.add_node("intent_planner", node_intent_planner)
            workflow.add_node("execution_planner", node_execution_planner)
            workflow.add_node("tool_executor", node_tool_executor)
            workflow.add_node("evidence_builder", node_evidence_builder)
            workflow.add_node("context_builder", node_context_builder)
            workflow.add_node("generator", node_generator)
            workflow.add_node("validator", node_validator)

            workflow.set_entry_point("firewall")
            workflow.add_conditional_edges("firewall", route_firewall)
            workflow.add_conditional_edges("governance", route_governance)
            workflow.add_edge("intent_planner", "execution_planner")
            workflow.add_edge("execution_planner", "tool_executor")
            workflow.add_edge("tool_executor", "evidence_builder")
            workflow.add_edge("evidence_builder", "context_builder")
            workflow.add_edge("context_builder", "generator")
            workflow.add_edge("generator", "validator")
            workflow.add_conditional_edges("validator", route_validator)

            return workflow.compile(checkpointer=mem_checkpointer)
        except Exception as e:
            logger.warning(f"[agent_graph] Native LangGraph compile failed, using FallbackStateGraphApp: {e}")

    return FallbackStateGraphApp(mem_checkpointer)


memory_checkpointer = MemorySaver()
agent_graph_app = build_sky_agent_graph(memory_checkpointer)
