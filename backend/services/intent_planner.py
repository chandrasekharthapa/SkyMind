"""SkyMind Intent Planner Service (Hybrid Mode with Phase 1.1 Observability).

Performs structured intent classification and entity extraction.
Hybrid Execution Flow: OpenAI Planner -> Fallback -> Rule-Based Planner.
Returns strongly-typed PlanningResult models and emits structured JSON telemetry logs.
"""

import re
import os
import time
import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from opentelemetry import metrics, trace

from backend.services.llm_provider import get_llm_provider, LLMProvider
from backend.services.langsmith_tracer import langsmith_tracer
from backend.services.openai_planner import openai_planner, PlanningResult

logger = logging.getLogger(__name__)

# OpenTelemetry Metrics & Tracer
meter = metrics.get_meter("skymind.planner")
tracer = trace.get_tracer("skymind.planner")

planner_latency_hist = meter.create_histogram(name="chat_planner_latency_seconds", description="Intent planner execution duration")
planner_confidence_hist = meter.create_histogram(name="chat_planner_confidence", description="Intent planner confidence score")
planner_failures_counter = meter.create_counter(name="chat_planner_failures_total", description="Intent planner failure count")
planner_timeouts_counter = meter.create_counter(name="chat_planner_timeouts_total", description="Intent planner timeout count")


CITY_TO_IATA = {
    "DELHI": "DEL", "NEW DELHI": "DEL",
    "MUMBAI": "BOM", "BOMBAY": "BOM",
    "BANGALORE": "BLR", "BENGALURU": "BLR",
    "CHENNAI": "MAA", "MADRAS": "MAA",
    "KOLKATA": "CCU", "CALCUTTA": "CCU",
    "HYDERABAD": "HYD",
    "GOA": "GOI",
    "COCHIN": "COK", "KOCHI": "COK",
    "BHUBANESWAR": "BBI",
    "AHMEDABAD": "AMD",
    "PUNE": "PNQ",
}

INTENT_REQUIRED_PARAMS = {
    "SEARCH_FLIGHTS": ["origin_iata", "destination_iata", "departure_date_iso"],
    "PREDICT_FARE": ["origin_iata", "destination_iata", "departure_date_iso"],
    "RECOMMEND_BEST": ["origin_iata", "destination_iata", "departure_date_iso"],
    "COMPARE_FLIGHTS": ["origin_iata", "destination_iata", "departure_date_iso"],
    "HISTORICAL_PRICE": ["origin_iata", "destination_iata", "departure_date_iso"],
    "ROUTE_INFO": ["origin_iata", "destination_iata"],
    "AIRPORT_INFO": [],
    "GREETING": [],
    "GENERAL_INQUIRY": []
}


def normalize_airport_code(text: str) -> Optional[str]:
    """Resolves city name or IATA code to 3-letter IATA code."""
    if not text:
        return None
    upper = text.strip().upper()
    if len(upper) == 3 and upper.isalpha():
        return upper
    return CITY_TO_IATA.get(upper)


def normalize_relative_date(date_str: str, base_date: Optional[datetime] = None) -> Optional[str]:
    """Normalizes relative date strings like 'tomorrow', 'next Friday', 'in 7 days' to YYYY-MM-DD."""
    if not date_str:
        return None
    
    today = base_date or datetime.now(timezone.utc)
    lowered = date_str.strip().lower()

    if lowered in ["today"]:
        return today.strftime("%Y-%m-%d")
    if lowered in ["tomorrow"]:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if lowered in ["day after tomorrow"]:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")

    match_days = re.search(r"in\s+(\d+)\s+days?", lowered)
    if match_days:
        num_days = int(match_days.group(1))
        return (today + timedelta(days=num_days)).strftime("%Y-%m-%d")

    match_iso = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", date_str)
    if match_iso:
        return match_iso.group(0)

    return None


class ExtractedEntities(BaseModel):
    cities: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)
    airlines: List[str] = Field(default_factory=list)


class NormalizedValues(BaseModel):
    origin_iata: Optional[str] = None
    destination_iata: Optional[str] = None
    departure_date_iso: Optional[str] = None
    airline_code: Optional[str] = None
    cabin_class: str = "ECONOMY"


class IntentClassification(BaseModel):
    intent: str = Field(description="Intent: SEARCH_FLIGHTS, PREDICT_FARE, RECOMMEND_BEST, COMPARE_FLIGHTS, AIRPORT_INFO, ROUTE_INFO, HISTORICAL_PRICE, GREETING, GENERAL_INQUIRY")
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    normalized_values: NormalizedValues = Field(default_factory=NormalizedValues)
    missing_parameters: List[str] = Field(default_factory=list)
    ambiguity: bool = False
    intent_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    entity_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    overall_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provider_used: str = Field(default="rule_based")


class IntentPlanner:
    """Hybrid Intent Planner supporting OpenAI Planner with Rule-Based Fallback and Telemetry."""

    def __init__(self, provider: Optional[LLMProvider] = None):
        self.planner_provider_name = os.getenv("INTENT_PLANNER_PROVIDER") or os.getenv("LLM_PROVIDER", "openai")
        self.provider = provider or get_llm_provider(self.planner_provider_name)

    def rule_based_plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> IntentClassification:
        """Deterministic rule-based fallback classification."""
        lowered = query.lower()
        
        # 1. Determine Intent
        intent = "GENERAL_INQUIRY"
        greetings = ["hello", "hi", "hey", "good morning", "good evening", "greetings"]
        if any(re.search(r"\b" + re.escape(w) + r"\b", lowered) for w in greetings):
            intent = "GREETING"
        elif any(w in lowered for w in ["predict", "fare forecast", "price trend", "prediction", "should i buy"]):
            intent = "PREDICT_FARE"
        elif any(w in lowered for w in ["recommend", "cheapest", "fastest", "best value"]):
            intent = "RECOMMEND_BEST"
        elif any(w in lowered for w in ["compare"]):
            intent = "COMPARE_FLIGHTS"
        elif any(w in lowered for w in ["history", "historical price", "past fares"]):
            intent = "HISTORICAL_PRICE"
        elif any(w in lowered for w in ["route", "fly to", "service to"]):
            intent = "ROUTE_INFO"
        elif any(w in lowered for w in ["airport", "terminal", "iata"]):
            intent = "AIRPORT_INFO"
        elif any(w in lowered for w in ["flight", "flights", "book", "find", "search", "ticket"]):
            intent = "SEARCH_FLIGHTS"

        # 2. Extract Cities & Airports
        cities_found = []
        for city_name, iata in CITY_TO_IATA.items():
            if re.search(r"\b" + re.escape(city_name.lower()) + r"\b", lowered):
                cities_found.append(city_name)
        
        origin_iata = None
        dest_iata = None
        if len(cities_found) >= 2:
            origin_iata = CITY_TO_IATA.get(cities_found[0])
            dest_iata = CITY_TO_IATA.get(cities_found[1])
        elif len(cities_found) == 1:
            dest_iata = CITY_TO_IATA.get(cities_found[0])

        # 3. Extract & Normalize Dates
        date_iso = None
        for date_keyword in ["tomorrow", "today", "day after tomorrow"]:
            if date_keyword in lowered:
                date_iso = normalize_relative_date(date_keyword)
                break
        
        if not date_iso:
            date_match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", query)
            if date_match:
                date_iso = date_match.group(0)

        # 4. Context Enrichment
        if context:
            origin_iata = origin_iata or context.get("origin")
            dest_iata = dest_iata or context.get("destination")
            date_iso = date_iso or context.get("departure_date")

        norm_vals = NormalizedValues(
            origin_iata=origin_iata,
            destination_iata=dest_iata,
            departure_date_iso=date_iso,
        )

        # 5. Missing Parameter Check
        required = INTENT_REQUIRED_PARAMS.get(intent, [])
        missing = [p for p in required if getattr(norm_vals, p, None) is None]
        is_ambiguity = len(missing) > 0 and intent not in ["GREETING", "GENERAL_INQUIRY"]

        intent_conf = 0.95 if intent != "GENERAL_INQUIRY" else 0.70
        entity_conf = 0.90 if len(cities_found) > 0 else 0.60
        overall_conf = round((intent_conf + entity_conf) / 2.0, 2)

        return IntentClassification(
            intent=intent,
            entities=ExtractedEntities(cities=cities_found, dates=[date_iso] if date_iso else []),
            normalized_values=norm_vals,
            missing_parameters=missing,
            ambiguity=is_ambiguity,
            intent_confidence=intent_conf,
            entity_confidence=entity_conf,
            overall_confidence=overall_conf,
            provider_used="rule_based"
        )

    async def plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> PlanningResult:
        """Hybrid Planning Entry Point: OpenAI Planner -> Fallback -> Rule-Based Planner with Phase 1.1 Telemetry."""
        t0 = time.perf_counter()
        
        with tracer.start_as_current_span("Planner") as span:
            # 1. Try OpenAI Planning Service
            try:
                with tracer.start_as_current_span("OpenAI Planner"):
                    res = await openai_planner.plan(query, context, timeout_seconds=3.0)

                latency_sec = (time.perf_counter() - t0)
                planner_latency_hist.record(latency_sec)
                planner_confidence_hist.record(res.confidence)
                
                # Emit Structured JSON Log
                logger.info(json.dumps({
                    "event": "planner_completed",
                    "planner_source": res.planner_source,
                    "planner_latency_ms": res.planner_latency_ms,
                    "planner_confidence": res.confidence,
                    "intent": res.intent,
                    "entities": res.entities,
                    "suggested_tools": res.required_tools,
                    "parallel_execution": res.parallel_execution,
                    "fallback_used": False,
                    "planner_error": None
                }))
                
                return res
            except Exception as e:
                planner_failures_counter.add(1)
                err_msg = str(e)

                # OpenTelemetry Fallback Span
                with tracer.start_as_current_span("Planner Fallback") as fallback_span:
                    fallback_span.set_attribute("fallback_reason", err_msg)
                    rb_res = self.rule_based_plan(query, context)

                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                latency_sec = latency_ms / 1000.0

                required_tools = []
                if rb_res.intent == "SEARCH_FLIGHTS":
                    required_tools = ["search_flights"]
                elif rb_res.intent == "PREDICT_FARE":
                    required_tools = ["predict_price", "forecast_prices"]
                elif rb_res.intent == "RECOMMEND_BEST":
                    required_tools = ["recommend_flights", "predict_price"]
                elif rb_res.intent == "COMPARE_FLIGHTS":
                    required_tools = ["compare_flights", "historical_prices"]
                elif rb_res.intent == "HISTORICAL_PRICE":
                    required_tools = ["historical_prices"]
                elif rb_res.intent == "ROUTE_INFO":
                    required_tools = ["route_information"]
                elif rb_res.intent == "AIRPORT_INFO":
                    required_tools = ["airport_information"]

                fallback_result = PlanningResult(
                    intent=rb_res.intent,
                    entities=rb_res.entities.model_dump(),
                    required_tools=required_tools,
                    execution_order=required_tools,
                    parallel_execution=True,
                    requires_clarification=rb_res.ambiguity,
                    confidence=rb_res.overall_confidence,
                    reasoning="Rule-based fallback classification",
                    fallback_used=True,
                    provider_used="rule_based",
                    planner_source="rule_based",
                    planner_latency_ms=latency_ms,
                    planner_success=False,
                    planner_error=err_msg
                )

                planner_latency_hist.record(latency_sec)
                planner_confidence_hist.record(fallback_result.confidence)

                # Emit Structured Fallback JSON Log
                logger.info(json.dumps({
                    "event": "planner_completed",
                    "planner_source": "rule_based",
                    "planner_latency_ms": latency_ms,
                    "planner_confidence": fallback_result.confidence,
                    "intent": fallback_result.intent,
                    "entities": fallback_result.entities,
                    "suggested_tools": fallback_result.required_tools,
                    "parallel_execution": fallback_result.parallel_execution,
                    "fallback_used": True,
                    "planner_error": err_msg
                }))

                return fallback_result

    async def plan_shadow(self, query: str, context: Optional[Dict[str, Any]] = None, timeout_seconds: float = 3.0) -> IntentClassification:
        """Legacy shadow interface maintained for backward compatibility."""
        return self.rule_based_plan(query, context)


intent_planner = IntentPlanner()
