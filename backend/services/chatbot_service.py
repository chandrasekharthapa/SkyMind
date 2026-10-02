"""Chatbot Orchestration Service.

Manages conversation state contexts, parallel tool calls, LLM generation loops,
validation steps, OpenTelemetry instrumentation metrics, and Phase 3.0 OpenAI LLM Judge Quality Assurance.
"""

import os
import json
import logging
import asyncio
import time
from collections import OrderedDict
from typing import List, Dict, Any, AsyncGenerator, Optional
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError
from opentelemetry import metrics, trace

from backend.services.llm_clients import DEFAULT_CHAT_CHAIN, ChatTarget, chat_targets
from backend.services.chatbot_tools import (
    TOOL_MAP, CONTEXT_FIELDS, accepted_params, execute_chatbot_tool,
)
from backend.services.chat_response_builder import ChatResponseBuilder
from backend.services.chat_response_validator import ChatResponseValidator
from backend.governance.models import GovernanceActionEnum

from backend.services.langsmith_tracer import langsmith_tracer, LangSmithTracer
from backend.services.intent_planner import intent_planner
from backend.services.execution_planner import execution_planner
from backend.services.evidence_builder import evidence_builder
from backend.services.prompt_builder import context_builder
from backend.services.judge_agent import judge_agent

logger = logging.getLogger(__name__)

# OpenTelemetry setup
meter = metrics.get_meter("skymind.chat")
tracer = trace.get_tracer("skymind.chat")

chat_latency_hist = meter.create_histogram(name="chat_latency_seconds", description="Total chat pipeline duration")
tool_latency_hist = meter.create_histogram(name="chat_tool_latency_seconds", description="Tool call duration")
llm_latency_hist = meter.create_histogram(name="chat_llm_latency_seconds", description="LLM duration")
hallucination_rejection_counter = meter.create_counter(name="chat_hallucination_rejections_total", description="Hallucination rejections count")
tool_failures_counter = meter.create_counter(name="chat_tool_failures_total", description="Tool execution failures count")
tokens_counter = meter.create_counter(name="chat_token_usage_total", description="Estimated total tokens used")
cost_counter = meter.create_counter(name="chat_estimated_cost_usd", description="Estimated USD cost")


def _slim_tool_result(result: Dict[str, Any], max_flights: int = 5) -> Dict[str, Any]:
    """Trim large tool results before passing to LLM to avoid context overflow."""
    if not isinstance(result, dict):
        return result
    slimmed = dict(result)
    for key in ("flights", "cheapest", "fastest", "best_value"):
        if key not in slimmed:
            continue
        val = slimmed[key]
        if isinstance(val, list):
            total = len(val)
            val = val[:max_flights]
            flights_slim = []
            for f in val:
                if isinstance(f, dict):
                    dep_time = f.get("departure_time")
                    arr_time = f.get("arrival_time")
                    duration = f.get("duration")
                    origin = f.get("origin")
                    destination = f.get("destination")
                    
                    if (not dep_time or not arr_time or not duration) and f.get("itineraries"):
                        itins = f.get("itineraries")
                        if isinstance(itins, list) and itins:
                            itin = itins[0]
                            if isinstance(itin, dict):
                                duration = duration or itin.get("duration")
                                segs = itin.get("segments")
                                if isinstance(segs, list) and segs:
                                    first_seg = segs[0]
                                    last_seg = segs[-1]
                                    if isinstance(first_seg, dict):
                                        dep_time = dep_time or first_seg.get("departure_time")
                                        origin = origin or first_seg.get("origin")
                                    if isinstance(last_seg, dict):
                                        arr_time = arr_time or last_seg.get("arrival_time")
                                        destination = destination or last_seg.get("destination")

                    flights_slim.append({
                        "flight_number": f.get("flight_number", ""),
                        "primary_airline": f.get("primary_airline", ""),
                        "primary_airline_name": f.get("primary_airline_name", ""),
                        "origin": origin or "",
                        "destination": destination or "",
                        "departure_time": dep_time or "",
                        "arrival_time": arr_time or "",
                        "duration": duration or "",
                        "price": f.get("price", 0),
                        "currency": f.get("currency", "INR"),
                        "seats_available": f.get("seats_available"),
                        "recommendation": (f.get("metadata") or {}).get("recommendation", "MONITOR"),
                        "advice": (f.get("metadata") or {}).get("advice", ""),
                    })
                else:
                    flights_slim.append(f)
            slimmed[key] = flights_slim
            if total > max_flights:
                slimmed[f"{key}_total"] = total
        elif isinstance(val, dict):
            slimmed[key] = {
                "flight_number": val.get("flight_number", ""),
                "primary_airline": val.get("primary_airline", ""),
                "primary_airline_name": val.get("primary_airline_name", ""),
                "price": val.get("price", 0),
                "currency": val.get("currency", "INR"),
                "recommendation": (val.get("metadata") or {}).get("recommendation", "MONITOR"),
            }
    return slimmed


NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
# The chat model is a chain, tried in order — see llm_clients.chat_targets and
# CHAT_MODELS. It was a single hard-wired NVIDIA model, meta/llama-3.1-70b-instruct,
# which NVIDIA retired on 2026-08-26 ("410 Gone"); every chat answer failed from
# then until 2026-10-01 and nothing noticed. A chain means one retired, overloaded
# or rate-limited model degrades the service instead of ending it.
# This name is kept for the evaluation logs that record which models served.
LLM_MODEL_ID = (
    os.getenv("CHAT_MODELS")
    or (f"nvidia:{os.getenv('CHAT_MODEL_ID')}" if os.getenv("CHAT_MODEL_ID") else None)
    or ",".join(f"{p}:{m}" for p, m in DEFAULT_CHAT_CHAIN)
)

# HTTP statuses after which the next model in the chain is tried: a key the
# provider rejects (401/403 — one bad key must not take chat down while another
# provider's works), gone or not found (a retired model), too large for the
# provider's token-per-minute budget (Groq answers 413), rate-limited, and
# server-side failures.
_FALLBACK_STATUSES = {401, 403, 404, 408, 409, 410, 413, 429, 500, 502, 503, 504}

# How many rounds of tool calls one turn may make before the model must answer.
# The old flow made exactly one: it ran the first batch of tools, then asked for
# the final answer while still offering the tools, and if the model used that
# second call to request another tool (look up an airport, then search it) the
# request was dropped, `content` was None, and the user got "Live data isn't
# available" for a route whose data had just been fetched.
MAX_TOOL_ROUNDS = int(os.getenv("CHAT_MAX_TOOL_ROUNDS", "3"))

# Conversation contexts kept in memory, least-recently-used evicted first. The
# dict this replaces was never pruned.
MAX_SESSIONS = int(os.getenv("CHAT_MAX_SESSIONS", "1000"))

NO_DATA_MESSAGE = "Live data isn't available for this route right now. Try again shortly."
UNVERIFIED_FARE_MESSAGE = (
    "I can only quote prices that come from live data. For fares, tell me the route and "
    "date (for example, \"DEL to BOM on 15 October\") and I'll look them up; for fees and "
    "charges, the airline's website has the current figures."
)
UNVERIFIED_ANSWER_MESSAGE = (
    "I couldn't verify that answer against SkyMind's data, so I've held it back. "
    "Try asking about a specific route and date."
)

_SYSTEM_PROMPT_TEMPLATE = """You are SkyMind, an aviation and air-travel assistant for travellers in India.

IDENTITY & TONE:
- Concise, accurate and practical, like a knowledgeable airline or airport desk agent.
- Use natural date styles ("{tomorrow_short}") and formatted prices ("₹9,330").
- Today is {today}; tomorrow is {tomorrow} (India time). Use these for relative
  dates, and take weekdays from them rather than working them out.
- Accept city names and common abbreviations for airports (e.g. "Bhubaneswar" or
  "BBSR" -> BBI). Search straight away when the route and date are clear; do not
  ask the user to confirm a code you could resolve.
- If the user names an airline, pass it as `airline` to search_flights.

TWO KINDS OF QUESTIONS:
1. Live data — fares, flight options, schedules, cheapest/fastest flights, price
   predictions or trends for a route and date. Use the tools. Every fare, flight
   number, time or route fact you state must come from tool output. If a tool fails
   or returns nothing, say: "Live data isn't available for this route right now. Try
   again shortly." If the route or date is missing, ask for it.
2. General aviation and air-travel knowledge — how flying works, what terms mean
   (layover, codeshare, PNR, red-eye), airport procedures (check-in, security,
   boarding, Digi Yatra), what to carry (ID, liquids, power banks), baggage
   concepts, delays and cancellations, jet lag, aircraft and safety. Answer these
   directly from your knowledge; no tool is needed.

RULES FOR KNOWLEDGE ANSWERS:
- Do not quote rupee amounts (fares, fees, charges, refunds) without tool data.
  Describe them qualitatively and suggest checking with the airline.
- Airline-specific rules (baggage allowances, change fees, check-in cut-offs) vary
  by airline and fare type and change over time. Give the typical rule for Indian
  domestic flights, say it is typical, and recommend confirming with the airline.
- For rights and regulations (refunds, compensation, denied boarding), give the
  general position and point to the airline or DGCA for the current rules.
- If you are not sure, say so. Never invent specifics.
- Keep to air travel. For anything unrelated, politely steer back to flights.
"""


def _build_system_prompt() -> str:
    # India time, not the server's UTC date: between midnight and 05:30 IST the
    # UTC date is still yesterday. Tomorrow is spelled out with its weekday
    # because the model computed weekdays itself and got them wrong ("tomorrow
    # (Monday, October 3)" on a Friday).
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    fmt = "%A, %B %d, %Y"
    tomorrow = now + timedelta(days=1)
    # The style example used to be a fixed "Monday, July 7", which the model
    # copied into replies as if it were a date — and July 7 is not a Monday in
    # 2026. A real date cannot carry a wrong weekday.
    return _SYSTEM_PROMPT_TEMPLATE.format(
        today=now.strftime(fmt), tomorrow=tomorrow.strftime(fmt),
        tomorrow_short=f"{tomorrow.strftime('%A, %B')} {tomorrow.day}")


def format_planner_prompt_section(planner_result: Optional[Any]) -> str:
    """Formats a structured advisory planning section to inject into the Primary LLM system prompt."""
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
        logger.warning(f"[ChatbotService] Failed to format planner prompt section: {e}")
        return ""


class ConversationContext:
    def __init__(self):
        self.origin: Optional[str] = None
        self.destination: Optional[str] = None
        self.departure_date: Optional[str] = None
        self.airline_code: Optional[str] = None
        self.cabin_class: str = "ECONOMY"

    def update_from_args(self, args: Dict[str, Any]) -> None:
        """Update context parameters from successful tool call arguments.

        Values come from the model's JSON, so they are not guaranteed to be
        strings; `.upper()` on a number raised and ended the turn.
        """
        def text(key: str) -> Optional[str]:
            value = args.get(key)
            return str(value).strip() if value not in (None, "") else None

        if text("origin"):
            self.origin = text("origin").upper()
        if text("destination"):
            self.destination = text("destination").upper()
        if text("departure_date"):
            self.departure_date = text("departure_date")
        if text("airline_code"):
            self.airline_code = text("airline_code").upper()
        if text("cabin_class"):
            self.cabin_class = text("cabin_class").upper()

    def seed_from_route(self, route: Optional[Dict[str, Any]]) -> None:
        """Fill unset fields from the results page the user is chatting on.

        The widget sends the route of the search page it is opened on; it was
        ignored, so "is this a good price?" asked from DEL->BOM results had no
        route. Only empty fields are filled — the conversation wins.
        """
        if not route:
            return
        if not self.origin and route.get("origin"):
            self.origin = str(route["origin"]).upper()
        if not self.destination and route.get("destination"):
            self.destination = str(route["destination"]).upper()
        if not self.departure_date and route.get("departure_date"):
            self.departure_date = str(route["departure_date"])
        if route.get("cabin_class") and self.cabin_class == "ECONOMY":
            self.cabin_class = str(route["cabin_class"]).upper()

    def to_system_prompt_addition(self) -> str:
        """Produce system context text for the LLM injection."""
        return (
            f"\n[CURRENT SEARCH CONTEXT STATE]:\n"
            f"- Origin: {self.origin or 'Not Set'}\n"
            f"- Destination: {self.destination or 'Not Set'}\n"
            f"- Departure Date: {self.departure_date or 'Not Set'}\n"
            f"- Preferred Airline: {self.airline_code or 'Not Set'}\n"
            f"- Cabin: {self.cabin_class}\n"
        )


from backend.services.memory_manager import memory_manager


class ChatbotService:
    def __init__(self, nvidia_client: Optional[AsyncOpenAI] = None):
        # An injected client (tests) is the whole chain; otherwise the chain is
        # built from the environment on first use.
        self.nvidia_client = nvidia_client
        self._targets: Optional[List[ChatTarget]] = None
        self.sessions: "OrderedDict[str, ConversationContext]" = OrderedDict()
        # Fire-and-forget tasks must be referenced until they finish, or the
        # event loop may garbage-collect them mid-run.
        self._background: set = set()

    def _chat_targets(self) -> List[ChatTarget]:
        if self.nvidia_client is not None:
            model = os.getenv("CHAT_MODEL_ID") or DEFAULT_CHAT_CHAIN[-1][1]
            return [ChatTarget(provider="injected", model=model, client=self.nvidia_client)]
        if self._targets is None:
            self._targets = chat_targets()
        if not self._targets:
            raise RuntimeError("No chat model configured: set GROQ_API_KEY and/or NVIDIA_API_KEY (or CHAT_MODELS).")
        return self._targets

    @staticmethod
    def _should_fall_back(exc: Exception) -> bool:
        if isinstance(exc, (APITimeoutError, APIConnectionError)):
            return True
        if isinstance(exc, APIStatusError):
            if exc.status_code in _FALLBACK_STATUSES:
                return True
            # Groq rejects a malformed tool call from the model with a 400
            # "tool_use_failed"; another model may well produce a valid one.
            return exc.status_code == 400 and "tool_use_failed" in str(exc)
        return False

    async def _complete(self, **kwargs: Any) -> Any:
        """One chat completion, from the first model in the chain that answers."""
        targets = self._chat_targets()
        last_error: Optional[Exception] = None
        for i, target in enumerate(targets):
            try:
                response = await target.client.chat.completions.create(model=target.model, **kwargs)
                if i:
                    logger.info(f"[ChatbotService] Answered by fallback model {target.label}")
                return response
            except Exception as e:
                if not self._should_fall_back(e) or i == len(targets) - 1:
                    raise
                last_error = e
                logger.warning(
                    f"[ChatbotService] {target.label} unavailable ({type(e).__name__}: "
                    f"{str(e)[:160]}); trying {targets[i + 1].label}"
                )
        raise last_error or RuntimeError("no chat model answered")

    def get_session_context(self, session_id: str) -> ConversationContext:
        if session_id in self.sessions:
            self.sessions.move_to_end(session_id)
            return self.sessions[session_id]

        ctx = ConversationContext()
        state = memory_manager.get_session_state(session_id)
        ctx.origin = state.origin
        ctx.destination = state.destination
        ctx.departure_date = state.departure_date
        self.sessions[session_id] = ctx
        while len(self.sessions) > MAX_SESSIONS:
            self.sessions.popitem(last=False)
        return ctx

    def sync_memory_manager(self, session_id: str, context: ConversationContext):
        memory_manager.update_session_state(session_id, {
            "origin": context.origin,
            "destination": context.destination,
            "departure_date": context.departure_date
        })

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Declare tool specifications for the LLM model."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_flights",
                    "description": "Searches for flights between origin and destination airports on a departure date.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string", "description": "3-letter IATA origin airport code (e.g., DEL)"},
                            "destination": {"type": "string", "description": "3-letter IATA destination airport code (e.g., BOM)"},
                            "departure_date": {"type": "string", "description": "Departure date in YYYY-MM-DD format"},
                            "cabin_class": {"type": "string", "default": "ECONOMY"},
                            "airline": {"type": "string", "description": "Only this airline's flights, if the user named one (e.g. \"Air India\", \"IndiGo\")"}
                        },
                        "required": ["origin", "destination", "departure_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "predict_price",
                    "description": "Predicts current price and gets recommendations/trends for a route.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string", "description": "3-letter IATA origin code"},
                            "destination": {"type": "string", "description": "3-letter IATA destination code"},
                            "departure_date": {"type": "string", "description": "YYYY-MM-DD format"},
                            "airline_code": {"type": "string", "description": "Optional 2-letter airline code"}
                        },
                        "required": ["origin", "destination", "departure_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "forecast_prices",
                    "description": "Gets 5-day fare forecasts and projections.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string", "description": "3-letter IATA code"},
                            "destination": {"type": "string", "description": "3-letter IATA code"},
                            "departure_date": {"type": "string", "description": "YYYY-MM-DD format"},
                            "airline_code": {"type": "string"}
                        },
                        "required": ["origin", "destination", "departure_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "recommend_flights",
                    "description": "Retrieves the Cheapest, Fastest, and Best Value flight options.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string", "description": "3-letter IATA code"},
                            "destination": {"type": "string", "description": "3-letter IATA code"},
                            "departure_date": {"type": "string", "description": "YYYY-MM-DD format"},
                            "cabin_class": {"type": "string", "default": "ECONOMY"}
                        },
                        "required": ["origin", "destination", "departure_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "compare_flights",
                    "description": "Compares flights side by side.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string", "description": "3-letter IATA code"},
                            "destination": {"type": "string", "description": "3-letter IATA code"},
                            "departure_date": {"type": "string", "description": "YYYY-MM-DD format"}
                        },
                        "required": ["origin", "destination", "departure_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "airport_information",
                    "description": "Searches for airports by city name or IATA code.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "City name, country, or code"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "route_information",
                    "description": "Checks if a specific route is supported in our platform.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string"},
                            "destination": {"type": "string"}
                        },
                        "required": ["origin", "destination"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "historical_prices",
                    "description": "Retrieves historical price logs.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string"},
                            "destination": {"type": "string"},
                            "departure_date": {"type": "string"}
                        },
                        "required": ["origin", "destination", "departure_date"]
                    }
                }
            }
        ]

    @staticmethod
    def _verified_summary(tool_payloads: List[Dict[str, Any]], context: ConversationContext) -> Optional[str]:
        """A deterministic answer built only from tool output, for when the
        model's own wording fails verification. Returns None if there is nothing
        verified to show."""
        for payload in tool_payloads:
            if not isinstance(payload, dict) or payload.get("status") != "success":
                continue
            try:
                if any(payload.get(k) for k in ("cheapest", "fastest", "best_value")):
                    return ChatResponseBuilder.build_recommendations_summary(payload)
                note = payload.get("note")
                flights = payload.get("flights")
                if note and not flights:
                    return note
                if flights:
                    shown = []
                    for f in flights[:5]:
                        f = dict(f)
                        price = f.get("price")
                        if isinstance(price, (int, float)) and (f.get("currency") in (None, "INR")):
                            f.setdefault("price_display", f"₹{price:,.0f}")
                        shown.append(f)
                    table = ChatResponseBuilder.build_flight_search_summary(
                        shown, context.origin or "", context.destination or ""
                    )
                    return f"{note}\n\n{table}" if note else table
            except Exception as e:  # the builder is a convenience, never a failure
                logger.warning(f"[ChatbotService] Verified summary failed: {e}")
        return None

    async def _run_tools(
        self,
        session_id: str,
        context: ConversationContext,
        tool_calls: List[Any],
        formatted_messages: List[Dict[str, Any]],
        planner_result: Any,
    ) -> List[Dict[str, Any]]:
        """Execute one round of tool calls, append them to the conversation, and
        return their raw payloads."""
        formatted_tool_calls = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
            }
            for tc in tool_calls
        ]
        formatted_messages.append({"role": "assistant", "content": None, "tool_calls": formatted_tool_calls})

        llm_tool_names = [tc["function"]["name"] for tc in formatted_tool_calls]
        suggested_tools = list(getattr(planner_result, "required_tools", []) or [])
        intersection = set(suggested_tools) & set(llm_tool_names)
        union = set(suggested_tools) | set(llm_tool_names)
        match_percent = round(len(intersection) / len(union) * 100.0, 2) if union else 100.0
        with tracer.start_as_current_span("Tool Comparison") as comp_span:
            comp_span.set_attribute("planner_vs_llm_match_percent", match_percent)
        logger.info(json.dumps({
            "event": "planner_vs_llm_comparison",
            "suggested_tools": suggested_tools,
            "llm_tool_calls": llm_tool_names,
            "planner_vs_llm_match_percent": match_percent,
        }))

        tasks, infos = [], []
        for tc in formatted_tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
                if not isinstance(args, dict):
                    args = {}
            except Exception:
                args = {}

            # Fill route fields the model left out from earlier turns — but only
            # fields this tool takes. Merging all three into every call is what
            # broke airport_information and route_information.
            params = accepted_params(name) or set()
            for key in CONTEXT_FIELDS:
                if key in params and not args.get(key) and getattr(context, key, None):
                    args[key] = getattr(context, key)

            infos.append((tc["id"], name, args))
            tasks.append(execute_chatbot_tool(name, args))

        t0 = time.perf_counter()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        tool_latency_hist.record(time.perf_counter() - t0)

        payloads, failed = [], []
        for (tool_id, name, args), result in zip(infos, results):
            if isinstance(result, Exception):
                tool_failures_counter.add(1, {"tool": name})
                failed.append(name)
                logger.error(f"Tool {name} raised: {result}")
                result = {"status": "error", "message": str(result)}
            elif isinstance(result, dict) and result.get("status") == "success":
                # Remember the route only from calls that worked, so a rejected
                # date or unknown city does not become the session's context.
                context.update_from_args(args)
            payloads.append(result)
            formatted_messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "name": name,
                "content": json.dumps(_slim_tool_result(result), default=str),
            })

        logger.info(json.dumps({
            "event": "tool_execution_completed",
            "tools_executed": llm_tool_names,
            "tool_execution_time_ms": round((time.perf_counter() - t0) * 1000, 2),
            "failed_tools": failed,
        }))

        task = asyncio.create_task(evidence_builder.build_shadow(session_id, payloads))
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return payloads

    async def chat_stream(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        route_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Run one conversational turn and yield the verified answer.

        The answer is yielded only after it has been checked against the tool
        output. The first model call used to be streamed straight to the user,
        so an answer that quoted fares without calling any tool reached the
        screen unverified; every path now goes through the same validator.
        """
        req_t0 = time.perf_counter()
        context = self.get_session_context(session_id)
        context.seed_from_route(route_context)

        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        latest_query = user_msgs[-1] if user_msgs else ""
        context_dict = {"origin": context.origin, "destination": context.destination, "departure_date": context.departure_date}

        parent_run_id = None
        full_output_text = ""
        try:
            planner_result = await intent_planner.plan(latest_query, context_dict)
            planner_prompt_section = format_planner_prompt_section(planner_result)

            full_system_prompt = (
                _build_system_prompt() + context.to_system_prompt_addition() + planner_prompt_section
            )
            formatted_messages: List[Dict[str, Any]] = [{"role": "system", "content": full_system_prompt}]
            for msg in messages:
                if msg.get("role") in ("user", "assistant"):
                    formatted_messages.append({"role": msg["role"], "content": msg["content"]})

            parent_run_id = langsmith_tracer.start_trace_request(session_id, latest_query, messages)
            langsmith_tracer.trace_tool_call(
                tool_name="planner_telemetry",
                args={"query": latest_query, "planner_source": planner_result.planner_source},
                result=planner_result.model_dump(),
                duration_seconds=planner_result.planner_latency_ms / 1000.0,
            )

            tool_payloads: List[Dict[str, Any]] = []
            tools_called = False
            final_text = ""
            for round_no in range(MAX_TOOL_ROUNDS + 1):
                # The last round withholds the tools, so the model has to answer.
                offer_tools = round_no < MAX_TOOL_ROUNDS
                kwargs: Dict[str, Any] = {"messages": formatted_messages}
                if offer_tools:
                    kwargs["tools"] = self.get_tool_definitions()
                llm_t0 = time.perf_counter()
                response = await self._complete(**kwargs)
                llm_latency_hist.record(time.perf_counter() - llm_t0)

                message = response.choices[0].message
                calls = list(getattr(message, "tool_calls", None) or [])
                if not calls or not offer_tools:
                    final_text = (message.content or "").strip()
                    break
                tools_called = True
                tool_payloads.extend(
                    await self._run_tools(session_id, context, calls, formatted_messages, planner_result)
                )

            is_valid = ChatResponseValidator.validate_llm_response(final_text, tool_payloads)
            val_errors = [] if is_valid else ["unverified fare or detail in response"]
            if not is_valid:
                hallucination_rejection_counter.add(1)
                logger.warning("[ChatbotService] Final answer failed verification; not shown.")

            should_run_judge, trigger_reason = judge_agent.should_trigger(
                validator_passed=is_valid,
                planner_confidence=planner_result.confidence,
                missing_tool_outputs=tools_called and not tool_payloads,
            )
            if should_run_judge:
                judge_res = await judge_agent.evaluate(
                    query=latest_query,
                    messages=messages,
                    planner_result=planner_result,
                    tool_payloads=tool_payloads,
                    primary_llm_response=final_text,
                    validator_passed=is_valid,
                    validation_errors=val_errors,
                    trigger_reason=trigger_reason,
                )
                langsmith_tracer.trace_tool_call(
                    tool_name="judge_evaluation",
                    args={"trigger_reason": trigger_reason},
                    result=judge_res.model_dump(),
                    duration_seconds=judge_res.judge_latency_ms / 1000.0,
                )
                if judge_res.decision == "REPAIR" and judge_res.repaired_response:
                    # The repair is another model's text. It used to replace the
                    # answer unchecked — including an answer the validator had just
                    # rejected for an invented fare — so the judge could put the
                    # hallucination straight back. It must pass the same check.
                    if ChatResponseValidator.validate_llm_response(judge_res.repaired_response, tool_payloads):
                        logger.info(f"[ChatbotService] Applying judge repair ({judge_res.repair_reason})")
                        final_text = judge_res.repaired_response
                        is_valid = True
                    else:
                        logger.warning("[ChatbotService] Judge repair failed verification; discarded.")

            if not is_valid:
                final_text = (
                    self._verified_summary(tool_payloads, context)
                    or (UNVERIFIED_ANSWER_MESSAGE if tools_called else UNVERIFIED_FARE_MESSAGE)
                )
            if not final_text:
                final_text = NO_DATA_MESSAGE if tools_called else UNVERIFIED_ANSWER_MESSAGE

            # Only worth persisting when there is a shared store behind it. Without
            # Redis, memory_manager is a second unbounded in-process dict holding
            # the same three fields this service already keeps.
            if getattr(memory_manager, "redis_client", None):
                self.sync_memory_manager(session_id, context)
            full_output_text = final_text
            yield final_text.encode("utf-8")

            total = time.perf_counter() - req_t0
            chat_latency_hist.record(total)
            logger.info(json.dumps({
                "event": "request_telemetry_completed",
                "total_request_latency_ms": round(total * 1000, 2),
                "tool_rounds_used": round_no,
                "validator_passed": is_valid,
            }))
            langsmith_tracer.end_trace_request(
                parent_run_id,
                {"response": full_output_text},
                LangSmithTracer.estimate_tokens(latest_query),
                LangSmithTracer.estimate_tokens(full_output_text),
            )

        except Exception as e:
            logger.error(f"ChatbotService error: {type(e).__name__}: {e}", exc_info=True)
            if parent_run_id is not None:
                langsmith_tracer.end_trace_request(parent_run_id, {"error": str(e)})
            if not full_output_text:
                yield b"Something went wrong. Please try your aviation question again."

chatbot_service = ChatbotService()
