"""SkyMind Context / Prompt Builder Service.

Centralizes the assembly of system instructions, business policies, conversation history,
planner outputs, evidence packages, user preferences, and generation settings into a
canonical CanonicalContext representation.

Includes Phase 2.0 Planner-Informed Prompt Construction utilities for augmenting LLM reasoning context.
"""

import time
import logging
import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from opentelemetry import metrics

from backend.services.intent_planner import IntentClassification
from backend.services.evidence_builder import EvidencePackage
from backend.services.langsmith_tracer import langsmith_tracer, LangSmithTracer

logger = logging.getLogger(__name__)

# OpenTelemetry Metrics
meter = metrics.get_meter("skymind.context_builder")
context_latency_hist = meter.create_histogram(name="chat_context_construction_latency_seconds", description="Context construction duration")
context_token_size_hist = meter.create_histogram(name="chat_context_token_size", description="Estimated context token count")
context_failures_counter = meter.create_counter(name="chat_context_failures_total", description="Context builder failure count")

DEFAULT_SYSTEM_INSTRUCTIONS = (
    "You are SkyMind, a premium Aviation Intelligence Platform.\n"
    "IDENTITY & TONE:\n"
    "- You are a concise, data-driven professional aviation assistant.\n"
    "- You speak in a helpful, professional tone (like Google Flights/Hopper).\n"
    "- Answer user queries using your registered evidence package facts."
)

DEFAULT_BUSINESS_POLICIES = [
    "You NEVER fabricate flight prices, schedules, or airport routes.",
    "Every fare, delay, or route fact must originate from provided EvidencePackage items.",
    "If evidence contains no data or fails, explain: 'Live pricing data isn't available for this route right now. Try again shortly.'",
    "Use natural date styles ('Monday, July 7') and formatted prices ('₹9,330')."
]


def format_planner_prompt_section(planner_result: Optional[Any]) -> str:
    """Formats a structured advisory planning section to inject into the Primary LLM system prompt.
    
    Returns an empty string if planner_result is None or invalid.
    """
    if not planner_result:
        return ""

    try:
        intent = getattr(planner_result, "intent", "UNKNOWN")
        confidence = getattr(planner_result, "confidence", 1.0)
        source = getattr(planner_result, "planner_source", "openai")
        entities = getattr(planner_result, "entities", {}) or {}
        tools = getattr(planner_result, "required_tools", []) or []
        parallel = getattr(planner_result, "parallel_execution", True)
        clarification = getattr(planner_result, "requires_clarification", False)

        lines = [
            "\n==================================================",
            "[ADVISORY AI PLANNING CONTEXT]",
            "The following planning context is advisory and intended to improve reasoning.",
            "",
            f"Intent:\n{intent}",
            "",
            f"Confidence:\n{confidence}",
            "",
            f"Planner Source:\n{source}",
            "",
            "Entities:"
        ]

        if isinstance(entities, dict) and entities:
            for k, v in entities.items():
                if v:
                    formatted_key = str(k).replace("_", " ").title()
                    lines.append(f"  {formatted_key}: {v}")
        else:
            lines.append("  None")

        lines.extend(["", "Suggested Tools:"])
        if tools:
            for tool in tools:
                lines.append(f"- {tool}")
        else:
            lines.append("- None")

        lines.extend([
            "",
            "Execution:",
            f"Parallel Execution: {str(parallel).lower()}",
            f"Requires Clarification: {str(clarification).lower()}"
        ])

        if clarification:
            lines.append("Advisory Note: Planner believes additional user clarification may be required before executing tools.")

        lines.append("==================================================\n")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[PromptBuilder] Failed to format planner prompt section: {e}")
        return ""


class GenerationSettings(BaseModel):
    temperature: float = 0.2
    max_tokens: int = 1000
    model_id: str = "meta/llama-3.1-70b-instruct"


class UserPreferences(BaseModel):
    preferred_airline: Optional[str] = None
    cabin_class: str = "ECONOMY"
    home_airport: Optional[str] = None


class CanonicalContext(BaseModel):
    session_id: str
    system_instructions: str = DEFAULT_SYSTEM_INSTRUCTIONS
    business_policies: List[str] = Field(default_factory=lambda: list(DEFAULT_BUSINESS_POLICIES))
    formatted_history: List[Dict[str, str]] = Field(default_factory=list)
    planner_summary: Optional[Dict[str, Any]] = None
    evidence_summary: Optional[Dict[str, Any]] = None
    user_preferences: UserPreferences = Field(default_factory=UserPreferences)
    generation_settings: GenerationSettings = Field(default_factory=GenerationSettings)
    full_prompt_text: str = ""
    estimated_token_count: int = 0
    construction_latency_seconds: float = 0.0


class ContextBuilder:
    """Canonical Context / Prompt Builder Service."""

    def build_context(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
        planner_output: Optional[IntentClassification] = None,
        evidence_package: Optional[EvidencePackage] = None,
        preferences: Optional[UserPreferences] = None,
        settings: Optional[GenerationSettings] = None
    ) -> CanonicalContext:
        """Assembles all context components into a deterministic CanonicalContext object."""
        start_time = time.time()
        user_prefs = preferences or UserPreferences()
        gen_settings = settings or GenerationSettings()

        # 1. Truncate / Format Conversation History (last 10 turns)
        history = []
        for msg in (messages or [])[-10:]:
            if isinstance(msg, dict) and msg.get("role") in ["user", "assistant"]:
                history.append({"role": msg["role"], "content": msg.get("content", "")})

        # 2. Extract Summaries
        planner_sum = planner_output.model_dump() if planner_output else None
        evidence_sum = evidence_package.model_dump() if evidence_package else None

        # 3. Assemble Canonical Prompt Text Deterministically
        prompt_sections = []
        prompt_sections.append(f"[SYSTEM INSTRUCTIONS]\n{DEFAULT_SYSTEM_INSTRUCTIONS}\n")
        
        prompt_sections.append("[BUSINESS POLICIES]")
        for policy in DEFAULT_BUSINESS_POLICIES:
            prompt_sections.append(f"- {policy}")
        prompt_sections.append("")

        if user_prefs.preferred_airline or user_prefs.home_airport:
            prompt_sections.append(
                f"[USER PREFERENCES]\n"
                f"- Home Airport: {user_prefs.home_airport or 'Not Set'}\n"
                f"- Preferred Airline: {user_prefs.preferred_airline or 'Not Set'}\n"
                f"- Cabin: {user_prefs.cabin_class}\n"
            )

        if planner_output:
            prompt_sections.append(
                f"[PLANNER CONTEXT]\n"
                f"- Classified Intent: {planner_output.intent}\n"
                f"- Ambiguity: {planner_output.ambiguity}\n"
                f"- Missing Parameters: {planner_output.missing_parameters}\n"
            )

        if evidence_package and evidence_package.items:
            prompt_sections.append(f"[EVIDENCE PACKAGE ({len(evidence_package.items)} Verified Items)]")
            for item in evidence_package.items:
                prompt_sections.append(f"• [{item.category}] {item.data}")
            prompt_sections.append("")

        if history:
            prompt_sections.append("[CONVERSATION HISTORY]")
            for h in history:
                prompt_sections.append(f"{h['role'].upper()}: {h['content']}")

        full_text = "\n".join(prompt_sections)
        token_count = LangSmithTracer.estimate_tokens(full_text)
        duration = time.time() - start_time

        return CanonicalContext(
            session_id=session_id,
            formatted_history=history,
            planner_summary=planner_sum,
            evidence_summary=evidence_sum,
            user_preferences=user_prefs,
            generation_settings=gen_settings,
            full_prompt_text=full_text,
            estimated_token_count=token_count,
            construction_latency_seconds=duration
        )

    async def build_shadow(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
        planner_output: Optional[IntentClassification] = None,
        evidence_package: Optional[EvidencePackage] = None,
        timeout_seconds: float = 2.0
    ) -> CanonicalContext:
        """Executes context building in non-blocking shadow mode."""
        start_time = time.time()
        try:
            ctx = await asyncio.wait_for(
                asyncio.to_thread(self.build_context, session_id, messages, planner_output, evidence_package),
                timeout=timeout_seconds
            )
            duration = time.time() - start_time

            # Record Telemetry
            context_latency_hist.record(duration)
            context_token_size_hist.record(ctx.estimated_token_count)

            logger.info(
                f"[ShadowContextBuilder] Session: {session_id} | "
                f"TokenCount: {ctx.estimated_token_count} | "
                f"HistoryTurns: {len(ctx.formatted_history)} | "
                f"Duration: {duration:.4f}s"
            )

            # LangSmith Shadow Trace
            langsmith_tracer.trace_tool_call(
                tool_name="shadow_context_builder",
                args={"session_id": session_id, "messages_count": len(messages or [])},
                result={"estimated_tokens": ctx.estimated_token_count, "latency_seconds": duration},
                duration_seconds=duration
            )

            return ctx

        except Exception as e:
            context_failures_counter.add(1)
            logger.warning(f"[ShadowContextBuilder] Context construction error (fail-safe): {e}")
            return CanonicalContext(session_id=session_id, construction_latency_seconds=time.time() - start_time)


context_builder = ContextBuilder()
