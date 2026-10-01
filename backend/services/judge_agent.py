"""OpenAI LLM Judge & Response Repair Service for SkyMind Copilot.

Evaluates Primary LLM responses against tool evidence packages and validation rules.
Triggers conditionally (e.g. validator failure, low planner confidence, random QA sampling).
Returns strongly typed JudgeResult models containing decision (PASS, REPAIR, CLARIFICATION, REGENERATE) and repaired text.
Does NOT execute tools, replace primary LLMs, or alter session state.
"""

import os
import json
import time
import random
import logging
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from opentelemetry import metrics, trace

logger = logging.getLogger(__name__)

# OpenTelemetry Setup
meter = metrics.get_meter("skymind.judge")
tracer = trace.get_tracer("skymind.judge")

judge_latency_hist = meter.create_histogram(name="chat_judge_latency_seconds", description="Judge evaluation duration")
judge_decisions_counter = meter.create_counter(name="chat_judge_decisions_total", description="Judge decision count")
judge_repairs_counter = meter.create_counter(name="chat_judge_repairs_total", description="Judge response repairs count")
judge_failures_counter = meter.create_counter(name="chat_judge_failures_total", description="Judge execution failures count")

from backend.services.llm_clients import resolve, parse_json_object, is_permanent_failure

# Provider, model and timeout come from JUDGE_PROVIDER / JUDGE_MODEL /
# JUDGE_TIMEOUT_SECONDS (see llm_clients). Without an OpenAI key the judge now
# runs on NVIDIA's hosted open models instead of never running at all.
_TARGET = resolve("JUDGE")
OPENAI_MODEL_ID = _TARGET.model if _TARGET else "none"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
JUDGE_ENABLED = os.getenv("JUDGE_ENABLED", "true").lower() not in ("false", "0")
JUDGE_SAMPLING_RATE = float(os.getenv("JUDGE_SAMPLING_RATE", "0.05"))


class JudgeResult(BaseModel):
    decision: str = Field(description="Decision: PASS, REPAIR, CLARIFICATION, REGENERATE")
    repaired_response: Optional[str] = Field(default=None, description="Repaired response text if decision is REPAIR")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list, description="List of identified issues or inconsistencies")
    repair_reason: Optional[str] = Field(default=None, description="Explanation for repair or intervention")
    judge_latency_ms: float = Field(default=0.0)
    judge_model: str = Field(default="gpt-4o-mini")
    judge_trigger_reason: str = Field(default="none")
    judge_success: bool = Field(default=True)


_SYSTEM_JUDGE_PROMPT = """You are an AI Quality Assurance Judge for SkyMind Aviation Intelligence.
Your responsibility is to evaluate the response produced by another AI.
Do not answer the user directly.

Determine whether the response:
• answers the user's request
• correctly uses tool outputs
• is factually consistent with the provided evidence
• omits important information
• contains contradictions
• is clear and concise
• requires clarification

Decision Criteria:
- Return PASS if the response is accurate and consistent with tool evidence.
- Return REPAIR with a corrected repaired_response if it contains minor factual contradictions, formatting issues, or hallucinated facts.
- Return CLARIFICATION if essential route parameters are missing.
- Return REGENERATE if the response is completely unhelpful or broken.

General-knowledge answers:
- Questions about how air travel works (terms, airport procedures, baggage concepts,
  documents, delays, aircraft) are answered from general knowledge and need no tool
  evidence. Do not REPAIR or REGENERATE such an answer for lacking tool output, and
  never replace it with a "no data available" message. Judge it on accuracy, on
  flagging airline-specific rules as typical, and on not quoting rupee amounts.

Rules:
- Never invent flight numbers, prices, or airports.
- Never modify exact numerical values from tool outputs.
- Never execute tools.
- Return JSON only.

Schema Requirements:
{
    "decision": "PASS",
    "repaired_response": null,
    "confidence": 0.98,
    "issues": [],
    "repair_reason": null
}
"""


class JudgeAgent:
    """OpenAI-powered Quality Assurance Judge Agent."""

    def __init__(self):
        self.target = _TARGET
        self.client = _TARGET.client if _TARGET else None
        self.enabled = JUDGE_ENABLED

    def should_trigger(
        self,
        validator_passed: bool,
        planner_confidence: float = 1.0,
        missing_tool_outputs: bool = False
    ) -> Tuple[bool, str]:
        """Evaluates whether the Judge agent should run on this request."""
        if not self.enabled:
            return False, "disabled"

        if not validator_passed:
            return True, "validator_failed"

        if planner_confidence < 0.70:
            return True, "low_planner_confidence"

        if missing_tool_outputs:
            return True, "missing_tool_outputs"

        if random.random() < JUDGE_SAMPLING_RATE:
            return True, "random_qa_sampling"

        return False, "none"

    async def evaluate(
        self,
        query: str,
        messages: List[Dict[str, Any]],
        planner_result: Optional[Any],
        tool_payloads: List[Dict[str, Any]],
        primary_llm_response: str,
        validator_passed: bool,
        validation_errors: List[str],
        trigger_reason: str = "none",
        timeout_seconds: float = 4.0
    ) -> JudgeResult:
        """Evaluates the Primary LLM response and produces a JudgeResult."""
        t0 = time.perf_counter()

        if not self.client:
            logger.warning("[JudgeAgent] Skipping evaluation: no judge model configured (JUDGE_PROVIDER / API key).")
            return JudgeResult(decision="PASS", judge_trigger_reason="no_api_key", judge_success=False)

        prompt_input = (
            f"User Query: {query}\n"
            f"Validator Passed: {validator_passed}\n"
            f"Validation Errors: {json.dumps(validation_errors)}\n"
            f"Tool Payloads Evidence: {json.dumps(tool_payloads[:3])}\n"
            f"Primary LLM Response: {primary_llm_response}"
        )

        with tracer.start_as_current_span("Judge") as span:
            span.set_attribute("trigger_reason", trigger_reason)
            try:
                with tracer.start_as_current_span("Judge Evaluation"):
                    kwargs: Dict[str, Any] = {}
                    if self.target.supports_json_mode:
                        kwargs["response_format"] = {"type": "json_object"}
                    response = await self.client.chat.completions.create(
                        model=self.target.model,
                        temperature=0.0,
                        messages=[
                            {"role": "system", "content": _SYSTEM_JUDGE_PROMPT},
                            {"role": "user", "content": prompt_input}
                        ],
                        timeout=max(timeout_seconds, self.target.timeout),
                        **kwargs,
                    )

                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                judge_latency_hist.record(latency_ms / 1000.0)

                content = response.choices[0].message.content or "{}"
                parsed = parse_json_object(content)

                parsed["judge_latency_ms"] = latency_ms
                parsed["judge_model"] = OPENAI_MODEL_ID
                parsed["judge_trigger_reason"] = trigger_reason
                parsed["judge_success"] = True

                result = JudgeResult.model_validate(parsed)
                judge_decisions_counter.add(1, {"decision": result.decision})

                if result.decision == "REPAIR" and result.repaired_response:
                    judge_repairs_counter.add(1)
                    with tracer.start_as_current_span("Judge Repair") as repair_span:
                        repair_span.set_attribute("repair_reason", result.repair_reason or "quality_improvement")

                # Emit Structured Telemetry JSON Log
                logger.info(json.dumps({
                    "event": "judge_completed",
                    "decision": result.decision,
                    "trigger_reason": trigger_reason,
                    "latency_ms": latency_ms,
                    "confidence": result.confidence,
                    "issues": result.issues,
                    "repair_reason": result.repair_reason,
                    "repair_performed": bool(result.decision == "REPAIR" and result.repaired_response)
                }))

                return result

            except Exception as e:
                judge_failures_counter.add(1)
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                logger.warning(f"[JudgeAgent] Judge evaluation error ({e}). Returning fallback PASS.")
                if is_permanent_failure(e):
                    logger.error("[JudgeAgent] That error will not clear by itself; judge off until restart.")
                    self.client = None
                return JudgeResult(
                    decision="PASS",
                    confidence=0.5,
                    issues=[f"Judge execution error: {str(e)}"],
                    judge_latency_ms=latency_ms,
                    judge_model=OPENAI_MODEL_ID,
                    judge_trigger_reason=trigger_reason,
                    judge_success=False
                )


judge_agent = JudgeAgent()
