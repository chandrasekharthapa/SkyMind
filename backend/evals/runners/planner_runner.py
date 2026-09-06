"""Hybrid Intent Planner Execution Runner with Full Provenance Traceability.

The result now carries `query` and `context`, the inputs that produced the plan.
Without them, an evaluator receiving only `expected` and `actual` could compare the
plan against the golden answer but could not check the plan against what was
*asked* — which is the one thing a groundedness check needs. Context matters as much
as the query on a follow-up turn ("what about Vistara for the same route?"), where
the route is in the context and only the carrier is in the query. It is provenance,
not a new measurement: the runner records what it ran.
"""

import time
import logging
from typing import Dict, Any
from backend.services.intent_planner import intent_planner

logger = logging.getLogger(__name__)


class PlannerRunner:
    """Executes target query against production Hybrid Intent Planner and records provenance."""

    async def run_single(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        query = test_case.get("inputs", {}).get("query", "")
        context = test_case.get("inputs", {}).get("context", {})

        t0 = time.perf_counter()
        plan_res = await intent_planner.plan(query, context)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        planner_src = getattr(plan_res, "planner_source", "hybrid")
        fallback_used = getattr(plan_res, "fallback_used", False)
        planner_err = getattr(plan_res, "planner_error", "")

        reason_text = planner_err if (fallback_used and planner_err) else ("Fallback activated" if fallback_used else "Executed primary planner")

        return {
            "query": query,
            "context": context,
            "intent": plan_res.intent,
            "entities": plan_res.entities,
            "required_tools": plan_res.required_tools,
            "requires_clarification": plan_res.requires_clarification,
            "confidence": plan_res.confidence,
            "planner_source": planner_src,
            "planner_model": "meta/llama-3.1-70b-instruct" if planner_src == "openai" else "rule_based_engine_v1",
            "planner_version": "1.1.0",
            "fallback_used": fallback_used,
            "planner_reason": reason_text,
            "planner_status": "FALLBACK" if fallback_used else "PRIMARY",
            "latency_ms": latency_ms
        }


planner_runner = PlannerRunner()
