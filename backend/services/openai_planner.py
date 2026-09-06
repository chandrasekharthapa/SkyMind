"""OpenAI Planning Service for SkyMind Copilot.

Analyzes user queries using OpenAI LLM Provider to return strongly-typed PlanningResult schemas.
Does NOT execute tools or generate user-facing answer text.
Instrumented for Phase 1.1 structured telemetry & latency metrics.
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

OPENAI_MODEL_ID = os.getenv("OPENAI_MODEL_ID") or os.getenv("PLANNER_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

AVAILABLE_TOOLS = [
    "search_flights",
    "predict_price",
    "forecast_prices",
    "recommend_flights",
    "compare_flights",
    "airport_information",
    "route_information",
    "historical_prices"
]

class PlanningResult(BaseModel):
    intent: str = Field(description="Primary intent e.g., SEARCH_FLIGHTS, PREDICT_FARE, RECOMMEND_BEST, COMPARE_FLIGHTS, AIRPORT_INFO, ROUTE_INFO, HISTORICAL_PRICE, GREETING, GENERAL_INQUIRY")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entities like origin, destination, departure_date, airline_code")
    required_tools: List[str] = Field(default_factory=list, description="List of tool names required from AVAILABLE_TOOLS")
    execution_order: List[str] = Field(default_factory=list, description="Ordered step identifiers or tool names")
    parallel_execution: bool = Field(default=True, description="Whether required tools can run concurrently")
    requires_clarification: bool = Field(default=False, description="True if essential route fields are missing")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str = Field(default="", description="Brief explanation of planning logic")
    fallback_used: bool = Field(default=False)
    provider_used: str = Field(default="openai")
    planner_source: str = Field(default="openai")
    planner_latency_ms: float = Field(default=0.0)
    planner_success: bool = Field(default=True)
    planner_error: Optional[str] = None


_SYSTEM_PLANNER_PROMPT = f"""You are the SkyMind Execution Planner.
You never answer users.
You only analyze user travel queries to determine intent and tool planning.
Return JSON only matching the schema.

AVAILABLE TOOLS:
{json.dumps(AVAILABLE_TOOLS)}

Schema Requirements:
{{
    "intent": "SEARCH_FLIGHTS",
    "entities": {{"origin": "DEL", "destination": "BOM", "departure_date": "2026-07-31"}},
    "required_tools": ["search_flights"],
    "execution_order": ["search_flights"],
    "parallel_execution": true,
    "requires_clarification": false,
    "confidence": 0.97,
    "reasoning": "User requested flights between Delhi and Mumbai"
}}
"""

class OpenAIPlanner:
    """OpenAI-powered planning service."""

    def __init__(self):
        self.api_key = OPENAI_API_KEY
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    async def plan(self, query: str, context: Optional[Dict[str, Any]] = None, timeout_seconds: float = 3.0) -> PlanningResult:
        """Invokes OpenAI model to parse query intent and tool execution plan."""
        t0 = time.perf_counter()
        if not self.client:
            raise ValueError("OPENAI_API_KEY is not configured.")

        prompt_input = (
            f"User Query: {query}\n"
            f"Search Context State: {json.dumps(context or {})}"
        )

        response = await self.client.chat.completions.create(
            model=OPENAI_MODEL_ID,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PLANNER_PROMPT},
                {"role": "user", "content": prompt_input}
            ],
            timeout=timeout_seconds
        )

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        content = response.choices[0].message.content
        if not content:
            raise ValueError("OpenAI returned empty completion content.")

        parsed = json.loads(content)
        parsed["fallback_used"] = False
        parsed["provider_used"] = "openai"
        parsed["planner_source"] = "openai"
        parsed["planner_latency_ms"] = latency_ms
        parsed["planner_success"] = True
        parsed["planner_error"] = None

        result = PlanningResult.model_validate(parsed)
        return result

openai_planner = OpenAIPlanner()
