"""OpenAI LLM Judge QA Execution Runner for Evaluation Platform."""

import time
import logging
from typing import Dict, Any
from backend.services.judge_agent import judge_agent

logger = logging.getLogger(__name__)


class JudgeRunner:
    """Executes target test cases against OpenAI LLM Judge Agent."""

    async def run_single(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        query = test_case.get("inputs", {}).get("query", "")
        primary_response = test_case.get("inputs", {}).get("primary_response", "Here are your flight options.")
        tool_payloads = test_case.get("inputs", {}).get("tool_payloads", [])
        validator_passed = test_case.get("inputs", {}).get("validator_passed", True)

        t0 = time.perf_counter()
        judge_res = await judge_agent.evaluate(
            query=query,
            messages=[{"role": "user", "content": query}],
            planner_result=None,
            tool_payloads=tool_payloads,
            primary_llm_response=primary_response,
            validator_passed=validator_passed,
            validation_errors=[] if validator_passed else ["hallucinated claim"],
            trigger_reason="evaluation_test"
        )
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        return {
            "decision": judge_res.decision,
            "repaired_response": judge_res.repaired_response,
            "confidence": judge_res.confidence,
            "issues": judge_res.issues,
            "repair_reason": judge_res.repair_reason,
            "latency_ms": latency_ms
        }


judge_runner = JudgeRunner()
