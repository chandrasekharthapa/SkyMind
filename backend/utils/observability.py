"""Observability Instrumentation.

Sets up OpenTelemetry tracing and metrics for tracking flight search latencies,
cache hit ratios, and exception/error rates.
"""

import time
import logging
from typing import Dict, Any
from opentelemetry import trace, metrics

logger = logging.getLogger(__name__)

# Tracer setup
tracer = trace.get_tracer("skymind.flights")

# Metrics setup
meter = metrics.get_meter("skymind.flights")

# Metrics counters & histograms
search_latency_histogram = meter.create_histogram(
    name="flight_search_latency_seconds",
    description="Measures E2E flight search duration in seconds",
    unit="s"
)

cache_hit_counter = meter.create_counter(
    name="flight_cache_hits_total",
    description="Total cache hits (Supabase price_history fallback)"
)

mcp_call_counter = meter.create_counter(
    name="mcp_api_calls_total",
    description="Total calls to the MCP search tool"
)

error_counter = meter.create_counter(
    name="pipeline_errors_total",
    description="Total runtime errors in the flight pipeline"
)

class ObservabilityTracker:
    @staticmethod
    def record_search_latency(seconds: float, status: str):
        search_latency_histogram.record(seconds, {"status": status})

    @staticmethod
    def record_cache_hit():
        cache_hit_counter.add(1)

    @staticmethod
    def record_mcp_call(provider: str = "google_flights"):
        mcp_call_counter.add(1, {"provider": provider})

    @staticmethod
    def record_error(error_type: str):
        error_counter.add(1, {"type": error_type})
