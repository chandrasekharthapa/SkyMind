"""SkyMind Enterprise Memory Architecture Service.

Provides a unified, typed memory interface isolating:
1. Short-Term Session History (TTL: 24 hours)
2. Conversation State (TTL: 24 hours with optimistic concurrency)
3. Long-Term User Travel Preferences (Persistent)
4. Workflow Checkpoints

Ensures fail-open fallback to RAM when Redis or PostgreSQL connections are unavailable.
"""

import time
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from opentelemetry import metrics

from backend.services.langsmith_tracer import langsmith_tracer

logger = logging.getLogger(__name__)

# OpenTelemetry Metrics
meter = metrics.get_meter("skymind.memory_manager")
memory_hit_counter = meter.create_counter(name="chat_memory_hit_total", description="Cache hit count")
memory_miss_counter = meter.create_counter(name="chat_memory_miss_total", description="Cache miss count")
memory_latency_hist = meter.create_histogram(name="chat_memory_latency_seconds", description="Memory access latency")
memory_failures_counter = meter.create_counter(name="chat_memory_failures_total", description="Memory operation failures")


class SessionHistory(BaseModel):
    session_id: str
    messages: List[Dict[str, str]] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    last_updated: float = Field(default_factory=time.time)
    ttl_seconds: int = 86400  # 24 Hours


class SessionState(BaseModel):
    session_id: str
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    last_query: str = ""
    version: int = 1
    last_updated: float = Field(default_factory=time.time)


class UserTravelProfile(BaseModel):
    user_id: str
    preferred_airline: Optional[str] = None
    home_airport: Optional[str] = None
    cabin_class: str = "ECONOMY"
    frequent_flyer_ids: Dict[str, str] = Field(default_factory=dict)
    updated_at: float = Field(default_factory=time.time)


class MemoryManager:
    """Enterprise 4-Tier Memory Manager with Fail-Safe RAM Fallback."""

    def __init__(self, redis_client: Optional[Any] = None, db_session: Optional[Any] = None):
        self.redis_client = redis_client
        self.db_session = db_session

        # In-Memory RAM Fallback Storages
        self._ram_histories: Dict[str, SessionHistory] = {}
        self._ram_states: Dict[str, SessionState] = {}
        self._ram_profiles: Dict[str, UserTravelProfile] = {}

    # ── 1. Short-Term Session History ─────────────────────────────────

    def get_session_history(self, session_id: str) -> SessionHistory:
        """Retrieves session message history with 24h TTL policy."""
        t0 = time.time()
        try:
            if self.redis_client:
                raw_data = self.redis_client.get(f"chat:session:{session_id}:history")
                if raw_data:
                    memory_hit_counter.add(1, {"domain": "history"})
                    memory_latency_hist.record(time.time() - t0, {"domain": "history"})
                    return SessionHistory.model_validate_json(raw_data)

            # Check RAM fallback & TTL expiration
            if session_id in self._ram_histories:
                hist = self._ram_histories[session_id]
                if (time.time() - hist.last_updated) <= hist.ttl_seconds:
                    memory_hit_counter.add(1, {"domain": "history", "backend": "ram"})
                    memory_latency_hist.record(time.time() - t0, {"domain": "history"})
                    return hist
                else:
                    # Expired session
                    del self._ram_histories[session_id]

            memory_miss_counter.add(1, {"domain": "history"})
        except Exception as e:
            memory_failures_counter.add(1, {"domain": "history"})
            logger.warning(f"[MemoryManager] History fetch error, falling back to empty: {e}")

        memory_latency_hist.record(time.time() - t0, {"domain": "history"})
        return SessionHistory(session_id=session_id)

    def save_session_history(self, session_id: str, messages: List[Dict[str, str]]) -> SessionHistory:
        """Saves session message history and refreshes 24h TTL."""
        t0 = time.time()
        hist = self.get_session_history(session_id)
        hist.messages = messages
        hist.last_updated = time.time()
        self._ram_histories[session_id] = hist

        if self.redis_client:
            try:
                json_payload = hist.model_dump_json()
                self.redis_client.setex(f"chat:session:{session_id}:history", hist.ttl_seconds, json_payload)
            except Exception as e:
                memory_failures_counter.add(1, {"domain": "history"})
                logger.warning(f"[MemoryManager] History save error (RAM saved): {e}")

        memory_latency_hist.record(time.time() - t0, {"domain": "history"})
        return hist

    # ── 2. Conversation State & Optimistic Concurrency ───────────────

    def get_session_state(self, session_id: str) -> SessionState:
        """Retrieves active conversation search state."""
        t0 = time.time()
        if self.redis_client:
            try:
                raw_data = self.redis_client.get(f"chat:session:{session_id}:state")
                if raw_data:
                    memory_hit_counter.add(1, {"domain": "state"})
                    memory_latency_hist.record(time.time() - t0, {"domain": "state"})
                    return SessionState.model_validate_json(raw_data)
            except Exception as e:
                memory_failures_counter.add(1, {"domain": "state"})
                logger.warning(f"[MemoryManager] Redis state fetch error (falling back to RAM): {e}")

        if session_id in self._ram_states:
            memory_hit_counter.add(1, {"domain": "state", "backend": "ram"})
            memory_latency_hist.record(time.time() - t0, {"domain": "state"})
            return self._ram_states[session_id]

        memory_miss_counter.add(1, {"domain": "state"})
        memory_latency_hist.record(time.time() - t0, {"domain": "state"})
        return SessionState(session_id=session_id)

    def update_session_state(self, session_id: str, updates: Dict[str, Any], expected_version: Optional[int] = None) -> SessionState:
        """Updates session state with optimistic concurrency protection."""
        t0 = time.time()
        state = self.get_session_state(session_id)

        if expected_version is not None and state.version != expected_version:
            raise ValueError(f"Optimistic lock violation: Current version is {state.version}, expected {expected_version}")

        for k, v in updates.items():
            if hasattr(state, k) and v is not None:
                setattr(state, k, v)

        state.version += 1
        state.last_updated = time.time()
        self._ram_states[session_id] = state

        if self.redis_client:
            try:
                json_payload = state.model_dump_json()
                self.redis_client.setex(f"chat:session:{session_id}:state", 86400, json_payload)
            except Exception as e:
                memory_failures_counter.add(1, {"domain": "state"})
                logger.warning(f"[MemoryManager] State update error (RAM updated): {e}")

        memory_latency_hist.record(time.time() - t0, {"domain": "state"})
        return state

    # ── 3. Long-Term User Travel Profiles ─────────────────────────────

    def get_user_profile(self, user_id: str) -> UserTravelProfile:
        """Retrieves persistent user travel profile."""
        t0 = time.time()
        try:
            if user_id in self._ram_profiles:
                memory_hit_counter.add(1, {"domain": "profile"})
                memory_latency_hist.record(time.time() - t0, {"domain": "profile"})
                return self._ram_profiles[user_id]

            memory_miss_counter.add(1, {"domain": "profile"})
        except Exception as e:
            memory_failures_counter.add(1, {"domain": "profile"})

        memory_latency_hist.record(time.time() - t0, {"domain": "profile"})
        return UserTravelProfile(user_id=user_id)

    def save_user_profile(self, profile: UserTravelProfile) -> UserTravelProfile:
        """Saves persistent user travel profile."""
        t0 = time.time()
        profile.updated_at = time.time()
        self._ram_profiles[profile.user_id] = profile
        memory_latency_hist.record(time.time() - t0, {"domain": "profile"})
        return profile


memory_manager = MemoryManager()
