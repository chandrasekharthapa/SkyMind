"""SkyMind Evidence Builder Service (Shadow Mode).

Consumes raw tool outputs to produce canonical, provider-agnostic EvidencePackages
with normalized currencies (INR), ISO-8601 timestamps, IATA airport codes,
deduplicated flight offers, deterministic derived metrics, and provenance tracking.
"""

import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from opentelemetry import metrics

from backend.services.intent_planner import normalize_airport_code
from backend.services.langsmith_tracer import langsmith_tracer

logger = logging.getLogger(__name__)

# OpenTelemetry Metrics
meter = metrics.get_meter("skymind.evidence_builder")
evidence_latency_hist = meter.create_histogram(name="chat_evidence_latency_seconds", description="Evidence generation duration")
evidence_items_hist = meter.create_histogram(name="chat_evidence_items_total", description="Count of evidence items generated")
evidence_dedup_ratio_hist = meter.create_histogram(name="chat_evidence_dedup_ratio", description="Deduplication ratio")
evidence_failures_counter = meter.create_counter(name="chat_evidence_failures_total", description="Evidence builder failure count")


class Provenance(BaseModel):
    tool_name: str
    execution_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_provider: str = "SkyMind Platform Data Engine"


class ConfidenceScore(BaseModel):
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str = "Deterministic verified tool output"


class EvidenceItem(BaseModel):
    id: str
    category: str  # FLIGHT_OFFER, PRICE_PREDICTION, FORECAST_DAY, AIRPORT_INFO, ROUTE_INFO, HISTORICAL_PRICE
    data: Dict[str, Any]
    provenance: Provenance
    confidence: ConfidenceScore = Field(default_factory=ConfidenceScore)


class EvidencePackage(BaseModel):
    session_id: str
    items: List[EvidenceItem] = Field(default_factory=list)
    summary_metrics: Dict[str, Any] = Field(default_factory=dict)
    deduplication_ratio: float = 0.0
    provenance_coverage: float = 1.0
    generation_latency_seconds: float = 0.0


def normalize_currency_amount(amount: Any, currency: str = "INR") -> Optional[float]:
    """Normalize a currency amount to a float in INR, or None if there isn't one.

    Returns `None` — not `0.0` — when the amount is absent or unparseable. It used
    to `return 0.0` from the `except`, and callers passed `payload.get("price",
    0.0)` in, so a tool response with no price produced an evidence item reading
    `price_inr: 0.0`. That is the worst available answer for a fare: it is a
    number the provider never sent, it is the minimum of any set it joins, and
    `prompt_builder` interpolates evidence items straight into the model prompt
    under a policy that says "You NEVER fabricate flight prices". A free flight is
    a fabrication; a null is the fact that the provider did not say.

    The USD rate below is still a hardcoded 85.0 and is a separate open item — it
    is a stale constant rather than an invented value, and no current provider
    path returns USD.
    """
    if amount is None:
        return None
    try:
        val = float(amount)
    except (ValueError, TypeError):
        logger.warning(
            "Evidence amount %r (currency %s) is not a number; recording it as "
            "null rather than ₹0.", amount, currency,
        )
        return None
    if val != val or val in (float("inf"), float("-inf")):
        logger.warning("Evidence amount %r is not finite; recording it as null.", amount)
        return None
    if currency.upper() in ["USD", "$"]:
        return round(val * 85.0, 2)
    return round(val, 2)


class EvidenceBuilder:
    """Canonical Evidence Builder Service."""

    def build_package(self, session_id: str, tool_payloads: List[Dict[str, Any]]) -> EvidencePackage:
        """Processes raw tool outputs into a canonical EvidencePackage."""
        start_time = time.time()
        raw_items_count = 0
        items: List[EvidenceItem] = []
        prices: List[float] = []

        seen_keys = set()

        for idx, payload in enumerate(tool_payloads or []):
            if not isinstance(payload, dict):
                continue

            tool_name = payload.get("_tool_name", f"tool_step_{idx}")
            status = payload.get("status", "success")
            if status != "success":
                continue

            # 1. Flights Search Output Parsing
            if "flights" in payload and isinstance(payload["flights"], list):
                for f in payload["flights"]:
                    raw_items_count += 1
                    # Was `f.get("flight_number", f"UNKNOWN_{raw_items_count}")`,
                    # `f.get("primary_airline", "6E")` and
                    # `f.get("primary_airline_name", "IndiGo")`. A flight the
                    # provider listed without a carrier was published to the
                    # chatbot's evidence package as an IndiGo flight, and one
                    # listed without a number was published as "UNKNOWN_4" — a
                    # string a model can and will quote back as a flight number.
                    # All three now stay null; the placeholder survives only
                    # inside the dedup key, where it never reaches a caller.
                    flight_num = f.get("flight_number") or None
                    airline = f.get("primary_airline") or None
                    airline_name = f.get("primary_airline_name") or None
                    price_raw = f.get("price")
                    price_val = price_raw.get("total") if isinstance(price_raw, dict) else price_raw
                    price_inr = normalize_currency_amount(price_val)

                    if price_inr is not None and price_inr > 0:
                        prices.append(price_inr)

                    dedup_key = (
                        f"{airline or '?'}_"
                        f"{flight_num or f'UNIDENTIFIED_{raw_items_count}'}_"
                        f"{price_inr}"
                    )
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    item = EvidenceItem(
                        id=f"ev_flight_{len(items)+1}",
                        category="FLIGHT_OFFER",
                        data={
                            "flight_number": flight_num,
                            "airline_code": airline,
                            "airline_name": airline_name,
                            "price_inr": price_inr,
                            "currency": "INR",
                            "seats_available": f.get("seats_available")
                        },
                        provenance=Provenance(tool_name=tool_name)
                    )
                    items.append(item)

            # 2. Prediction Output Parsing
            elif "predicted_price" in payload:
                raw_items_count += 1
                pred_price = normalize_currency_amount(payload["predicted_price"])
                if pred_price is not None and pred_price > 0:
                    prices.append(pred_price)

                item = EvidenceItem(
                    id=f"ev_pred_{len(items)+1}",
                    category="PRICE_PREDICTION",
                    data={
                        "predicted_price_inr": pred_price,
                        "currency": "INR",
                        "recommendation_action": payload.get("recommendation", {}).get("action", "WAIT") if isinstance(payload.get("recommendation"), dict) else "WAIT",
                        "trend": payload.get("recommendation", {}).get("trend", "STABLE") if isinstance(payload.get("recommendation"), dict) else "STABLE"
                    },
                    provenance=Provenance(tool_name=tool_name)
                )
                items.append(item)

                if "forecast" in payload and isinstance(payload["forecast"], list):
                    for fc in payload["forecast"]:
                        raw_items_count += 1
                        # The `, 0.0` defaults are gone from all three. A forecast
                        # point that arrives without bounds used to be published
                        # with `lower_bound_inr: 0.0` and `upper_bound_inr: 0.0`,
                        # which is not a wide interval or a missing one — it is an
                        # inverted interval asserting the fare cannot exceed zero,
                        # handed to the model as a verified fact. `interval_basis`
                        # travels with it so the bounds' provenance survives into
                        # the evidence package too.
                        fc_price = normalize_currency_amount(fc.get("price"))
                        fc_data = {
                            "date": fc.get("date"),
                            "price_inr": fc_price,
                            "lower_bound_inr": normalize_currency_amount(fc.get("lower")),
                            "upper_bound_inr": normalize_currency_amount(fc.get("upper")),
                            "currency": "INR"
                        }
                        basis = fc.get("interval_basis")
                        if isinstance(basis, dict):
                            fc_data["interval_basis"] = basis
                        items.append(EvidenceItem(
                            id=f"ev_fc_{len(items)+1}",
                            category="FORECAST_DAY",
                            data=fc_data,
                            provenance=Provenance(tool_name=tool_name)
                        ))

            # 3. Airport Info Parsing
            elif "airports" in payload and isinstance(payload["airports"], list):
                for ap in payload["airports"]:
                    raw_items_count += 1
                    iata = normalize_airport_code(ap.get("iata_code") or ap.get("code") or "")
                    if iata and iata not in seen_keys:
                        seen_keys.add(iata)
                        items.append(EvidenceItem(
                            id=f"ev_ap_{len(items)+1}",
                            category="AIRPORT_INFO",
                            data={
                                "iata_code": iata,
                                "name": ap.get("name"),
                                "city": ap.get("city")
                            },
                            provenance=Provenance(tool_name=tool_name)
                        ))

            # 4. Route Info Parsing
            elif "supported" in payload:
                raw_items_count += 1
                items.append(EvidenceItem(
                    id=f"ev_route_{len(items)+1}",
                    category="ROUTE_INFO",
                    data={
                        "origin": normalize_airport_code(payload.get("origin", "")),
                        "destination": normalize_airport_code(payload.get("destination", "")),
                        "supported": payload.get("supported", True)
                    },
                    provenance=Provenance(tool_name=tool_name)
                ))

            # 5. Historical Prices Parsing
            elif "data" in payload and isinstance(payload["data"], list):
                for hp in payload["data"]:
                    raw_items_count += 1
                    hp_price = normalize_currency_amount(hp.get("price"))
                    items.append(EvidenceItem(
                        id=f"ev_hist_{len(items)+1}",
                        category="HISTORICAL_PRICE",
                        data={
                            "price_inr": hp_price,
                            "recorded_at": hp.get("recorded_at"),
                            "currency": "INR"
                        },
                        provenance=Provenance(tool_name=tool_name)
                    ))

        # Compute Summary & Metrics
        dedup_ratio = round(1.0 - (len(items) / max(raw_items_count, 1)), 2)
        summary = {
            "item_count": len(items),
            "currencies_present": ["INR"],
            "min_price_inr": min(prices) if prices else None,
            "max_price_inr": max(prices) if prices else None,
            # Was `else 0.0`. With one price or none there is no spread, and ₹0
            # spread is a claim of a perfectly uniform market rather than an
            # absence of one — the same shape as the bounds above.
            "price_spread_inr": round(max(prices) - min(prices), 2) if len(prices) >= 2 else None
        }

        duration = time.time() - start_time

        return EvidencePackage(
            session_id=session_id,
            items=items,
            summary_metrics=summary,
            deduplication_ratio=max(0.0, dedup_ratio),
            provenance_coverage=1.0 if items else 0.0,
            generation_latency_seconds=duration
        )

    async def build_shadow(self, session_id: str, tool_payloads: List[Dict[str, Any]], timeout_seconds: float = 2.0) -> EvidencePackage:
        """Executes evidence building in non-blocking shadow mode."""
        start_time = time.time()
        try:
            package = await asyncio.wait_for(
                asyncio.to_thread(self.build_package, session_id, tool_payloads),
                timeout=timeout_seconds
            )
            duration = time.time() - start_time

            # Record Telemetry
            evidence_latency_hist.record(duration)
            evidence_items_hist.record(len(package.items))
            evidence_dedup_ratio_hist.record(package.deduplication_ratio)

            logger.info(
                f"[ShadowEvidenceBuilder] Session: {session_id} | "
                f"Items: {len(package.items)} | "
                f"DedupRatio: {package.deduplication_ratio} | "
                f"Duration: {duration:.4f}s"
            )

            # LangSmith Shadow Trace
            langsmith_tracer.trace_tool_call(
                tool_name="shadow_evidence_builder",
                args={"session_id": session_id, "raw_payloads_count": len(tool_payloads or [])},
                result=package.model_dump(),
                duration_seconds=duration
            )

            return package

        except Exception as e:
            evidence_failures_counter.add(1)
            logger.warning(f"[ShadowEvidenceBuilder] Evidence building error (fail-safe): {e}")
            return EvidencePackage(session_id=session_id, generation_latency_seconds=time.time() - start_time)


evidence_builder = EvidenceBuilder()
