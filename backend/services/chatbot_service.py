"""Chatbot Orchestration Service.

Manages conversation state contexts, parallel tool calls, LLM generation loops,
validation steps, OpenTelemetry instrumentation metrics, and Phase 3.0 OpenAI LLM Judge Quality Assurance.
"""

import os
import json
import logging
import asyncio
import time
from typing import List, Dict, Any, AsyncGenerator, Optional
from openai import AsyncOpenAI
from opentelemetry import metrics, trace

from backend.services.chatbot_tools import TOOL_MAP, execute_chatbot_tool
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


# NVIDIA Llama Infrastructure
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
LLM_MODEL_ID = "meta/llama-3.1-70b-instruct"

_SYSTEM_PROMPT_TEMPLATE = """You are SkyMind, a premium Aviation Intelligence Platform.

IDENTITY & TONE:
- You are a concise, data-driven professional aviation assistant.
- You speak in a helpful, professional tone (like Google Flights/Hopper). No general conversational filler.
- Answer user queries using your registered tool set.

TOOL USAGE & TRUTH:
- You NEVER fabricate flight prices, schedules, or airport routes.
- Every fare, delay, or route fact must originate from tool output.
- If a tool returns no data or fails, explain: "Live data isn't available for this route right now. Try again shortly."
- Use natural date styles ("Monday, July 7") and formatted prices ("₹9,330").
- Today's date is {today}. Use this to resolve relative dates like 'tomorrow' or 'next week'.
"""


def _build_system_prompt() -> str:
    from datetime import date
    today = date.today().strftime("%A, %B %d, %Y")
    return _SYSTEM_PROMPT_TEMPLATE.format(today=today)


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
        """Update context parameters from successful tool call arguments."""
        if args.get("origin"):
            self.origin = args["origin"].upper()
        if args.get("destination"):
            self.destination = args["destination"].upper()
        if args.get("departure_date"):
            self.departure_date = args["departure_date"]
        if args.get("airline_code"):
            self.airline_code = args["airline_code"].upper()
        if args.get("cabin_class"):
            self.cabin_class = args["cabin_class"]

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


from backend.services.llm_provider import get_llm_provider
from backend.services.memory_manager import memory_manager

class ChatbotService:
    def __init__(self):
        self.nvidia_client = AsyncOpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=NVIDIA_API_KEY,
        )
        self.llm_provider = get_llm_provider()
        self.sessions: Dict[str, ConversationContext] = {}

    def get_session_context(self, session_id: str) -> ConversationContext:
        if session_id not in self.sessions:
            ctx = ConversationContext()
            state = memory_manager.get_session_state(session_id)
            ctx.origin = state.origin
            ctx.destination = state.destination
            ctx.departure_date = state.departure_date
            self.sessions[session_id] = ctx

        return self.sessions[session_id]

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
                            "cabin_class": {"type": "string", "default": "ECONOMY"}
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

    async def chat_stream(self, session_id: str, messages: List[Dict[str, Any]]) -> AsyncGenerator[bytes, None]:
        """Runs conversational flow, executing tools and validation checks before outputting chunks."""
        req_t0 = time.perf_counter()
        context = self.get_session_context(session_id)
        
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        latest_query = user_msgs[-1] if user_msgs else ""
        context_dict = {"origin": context.origin, "destination": context.destination, "departure_date": context.departure_date}
        
        # ── Phase 1.1: Hybrid OpenAI Intent Planner ──────────────────────
        planner_result = await intent_planner.plan(latest_query, context_dict)

        # ── Phase 2.0: Planner-Informed System Prompt Construction ─────────
        planner_prompt_section = format_planner_prompt_section(planner_result)
        is_injected = bool(planner_prompt_section)
        section_size = len(planner_prompt_section)
        planner_tokens = len(planner_prompt_section.split()) if is_injected else 0

        logger.info(json.dumps({
            "event": "planner_context_injected",
            "planner_context_injected": is_injected,
            "prompt_planner_section_size": section_size,
            "planner_prompt_tokens": planner_tokens
        }))

        # Inject conversation history & advisory planner context into system prompt
        full_system_prompt = _build_system_prompt() + context.to_system_prompt_addition() + planner_prompt_section
        
        formatted_messages = [{"role": "system", "content": full_system_prompt}]
        for msg in messages:
            if msg.get("role") in ["user", "assistant"]:
                formatted_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        parent_run_id = langsmith_tracer.start_trace_request(session_id, latest_query, messages)
        full_output_text = ""

        # Attach Planner Observability Metadata to LangSmith Trace
        langsmith_tracer.trace_tool_call(
            tool_name="planner_telemetry",
            args={"query": latest_query, "planner_source": planner_result.planner_source},
            result=planner_result.model_dump(),
            duration_seconds=planner_result.planner_latency_ms / 1000.0
        )

        try:
            llm_start = time.perf_counter()
            response = await self.nvidia_client.chat.completions.create(
                model=LLM_MODEL_ID,
                messages=formatted_messages,
                tools=self.get_tool_definitions(),
                stream=True
            )
            llm_latency_hist.record(time.perf_counter() - llm_start)

            tool_calls = {}
            streamed_text = ""
            stream_start = time.perf_counter()

            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    streamed_text += delta.content
                    full_output_text += delta.content
                    yield delta.content.encode("utf-8")

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index not in tool_calls:
                            tool_calls[tc.index] = {
                                "id": tc.id,
                                "function": {"name": tc.function.name, "arguments": ""},
                            }
                        if tc.function.arguments:
                            tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments

            streaming_duration_ms = round((time.perf_counter() - stream_start) * 1000, 2)

            # ── Execute Tool Calls in Parallel ──────────────────────────
            if tool_calls:
                formatted_tool_calls = []
                for idx, tc in tool_calls.items():
                    formatted_tool_calls.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        }
                    })
                formatted_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": formatted_tool_calls
                })

                # ── Runtime Planner vs. LLM Tool Comparison ─────────────
                llm_tool_names = [tc["function"]["name"] for tc in formatted_tool_calls]
                suggested_tools = planner_result.required_tools

                planner_missing = [t for t in llm_tool_names if t not in suggested_tools]
                planner_extra = [t for t in suggested_tools if t not in llm_tool_names]
                
                intersection = set(suggested_tools).intersection(set(llm_tool_names))
                union = set(suggested_tools).union(set(llm_tool_names))
                match_percent = round((len(intersection) / len(union)) * 100.0, 2) if union else 100.0

                with tracer.start_as_current_span("Tool Comparison") as comp_span:
                    comp_span.set_attribute("planner_vs_llm_match_percent", match_percent)
                    comp_span.set_attribute("planner_missing_count", len(planner_missing))
                    comp_span.set_attribute("planner_extra_count", len(planner_extra))

                # Emit Structured JSON Log for Comparison
                logger.info(json.dumps({
                    "event": "planner_vs_llm_comparison",
                    "suggested_tools": suggested_tools,
                    "llm_tool_calls": llm_tool_names,
                    "planner_vs_llm_match_percent": match_percent,
                    "planner_missing_tools": planner_missing,
                    "planner_extra_tools": planner_extra,
                    "llm_extra_tools": planner_missing
                }))

                # Prepare parallel coroutines
                tasks = []
                tool_info_list = []
                for idx, tc in tool_calls.items():
                    tool_name = tc["function"]["name"]
                    tool_args_str = tc["function"]["arguments"]
                    tool_id = tc["id"]
                    
                    try:
                        tool_args = json.loads(tool_args_str)
                    except Exception:
                        tool_args = {}

                    # Enrich tool_args with missing fields from context
                    for key in ["origin", "destination", "departure_date"]:
                        if key not in tool_args and getattr(context, key, None):
                            tool_args[key] = getattr(context, key)

                    # Update context with new state parameters
                    context.update_from_args(tool_args)

                    tool_info_list.append((tool_id, tool_name, tool_args))
                    tasks.append(execute_chatbot_tool(tool_name, tool_args))

                # Execute tasks concurrently
                tool_t0 = time.perf_counter()
                tool_results = await asyncio.gather(*tasks, return_exceptions=True)
                tool_execution_time_ms = round((time.perf_counter() - tool_t0) * 1000, 2)
                tool_latency_hist.record(tool_execution_time_ms / 1000.0)

                tool_payloads = []
                failed_tools = []
                for idx, result in enumerate(tool_results):
                    tool_id, tool_name, tool_args = tool_info_list[idx]
                    
                    if isinstance(result, Exception):
                        tool_failures_counter.add(1, {"tool": tool_name})
                        failed_tools.append(tool_name)
                        logger.error(f"Concurrent tool execution error: {result}")
                        result = {"status": "error", "message": str(result)}
                    
                    tool_payloads.append(result)

                    # Slim result for LLM context
                    llm_content = _slim_tool_result(result)
                    formatted_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": json.dumps(llm_content)
                    })

                # Emit Structured Tool Execution JSON Log
                logger.info(json.dumps({
                    "event": "tool_execution_completed",
                    "tools_executed": llm_tool_names,
                    "tool_execution_time_ms": tool_execution_time_ms,
                    "parallel_batches": 1,
                    "failed_tools": failed_tools
                }))

                # Execute shadow evidence builder (non-blocking)
                asyncio.create_task(evidence_builder.build_shadow(session_id, tool_payloads))

                # Run final LLM generation step based on tool details
                if tool_payloads:
                    final_res = await self.nvidia_client.chat.completions.create(
                        model=LLM_MODEL_ID,
                        messages=formatted_messages,
                        tools=self.get_tool_definitions(),
                        stream=False
                    )
                    
                    final_text = final_res.choices[0].message.content or ""

                    # Verify response logic
                    is_valid = ChatResponseValidator.validate_llm_response(final_text, tool_payloads)
                    val_errors = [] if is_valid else ["detected hallucinated fields in response"]
                    if not is_valid:
                        hallucination_rejection_counter.add(1)
                        logger.warning("Rejection trigger: detected hallucinated fields in final LLM response.")
                        final_text = "Live pricing data isn't available for this route right now. Try again shortly."

                    # ── Phase 3.0: OpenAI LLM Judge Quality Assurance Check ────
                    should_run_judge, trigger_reason = judge_agent.should_trigger(
                        validator_passed=is_valid,
                        planner_confidence=planner_result.confidence,
                        missing_tool_outputs=not tool_payloads if tool_calls else False
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
                            trigger_reason=trigger_reason
                        )

                        # Attach Judge Telemetry to LangSmith Trace
                        langsmith_tracer.trace_tool_call(
                            tool_name="judge_evaluation",
                            args={"trigger_reason": trigger_reason},
                            result=judge_res.model_dump(),
                            duration_seconds=judge_res.judge_latency_ms / 1000.0
                        )

                        if judge_res.decision == "REPAIR" and judge_res.repaired_response:
                            logger.info(f"[ChatbotService] Applying Judge Repair (reason: {judge_res.repair_reason})")
                            final_text = judge_res.repaired_response

                    full_output_text = final_text
                    if final_text:
                        yield final_text.encode("utf-8")
                    else:
                        fallback = "Live data isn't available for this route right now. Try again shortly."
                        full_output_text = fallback
                        yield fallback.encode("utf-8")

                    total_latency_ms = round((time.perf_counter() - req_t0) * 1000, 2)
                    
                    # Emit Request Final Telemetry Log
                    logger.info(json.dumps({
                        "event": "request_telemetry_completed",
                        "total_request_latency_ms": total_latency_ms,
                        "streaming_duration_ms": streaming_duration_ms,
                        "validator_passed": is_valid,
                        "validator_errors": val_errors
                    }))

            total_latency_sec = time.perf_counter() - req_t0
            chat_latency_hist.record(total_latency_sec)

            # End LangSmith parent trace
            p_tokens = LangSmithTracer.estimate_tokens(latest_query)
            c_tokens = LangSmithTracer.estimate_tokens(full_output_text)
            langsmith_tracer.end_trace_request(parent_run_id, {"response": full_output_text}, p_tokens, c_tokens)

        except Exception as e:
            logger.error(f"ChatbotService error: {e}")
            langsmith_tracer.end_trace_request(parent_run_id, {"error": str(e)})
            if not full_output_text:
                yield b"Something went wrong. Please try your aviation question again."

chatbot_service = ChatbotService()
