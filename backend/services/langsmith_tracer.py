"""LangSmith Tracing and Instrumentation Service.

Provides robust, fail-open observability instrumentation for LLM requests,
tool calls, planner steps, token metrics, and evaluation tracking alongside OpenTelemetry.
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import dotenv

logger = logging.getLogger(__name__)

# Ensure environment variables are loaded from backend/.env or root .env
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

COST_PER_1K_PROMPT = 0.0007
COST_PER_1K_COMPLETION = 0.0009


class LangSmithTracer:
    """Fail-open LangSmith tracing manager for SkyMind Conversational Platform."""

    def __init__(self):
        self.enabled = (
            os.getenv("LANGSMITH_TRACING", "false").lower() in ("true", "1")
            or os.getenv("LANGCHAIN_TRACING_V2", "false").lower() in ("true", "1")
        )
        self.api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
        self.project_name = os.getenv("LANGSMITH_PROJECT", "skymind-concierge")
        
        self.client = None
        if self.enabled and self.api_key:
            try:
                from langsmith import Client
                self.client = Client(api_key=self.api_key)
                logger.info(f"[LangSmithTracer] Initialized LangSmith Client for project '{self.project_name}'.")
            except Exception as e:
                logger.warning(f"[LangSmithTracer] Could not initialize LangSmith Client: {e}. Falling back to standard logging.")
                self.client = None

    def start_trace_request(self, session_id: str, query: str, messages: list) -> Optional[str]:
        """Starts a top-level parent run for a chat request. Returns run_id string."""
        if not self.client:
            return None
        try:
            run_id = str(uuid.uuid4())
            self.client.create_run(
                id=run_id,
                name="chat_request",
                run_type="chain",
                inputs={"query": query, "messages": messages},
                project_name=self.project_name,
                extra={"session_id": session_id},
                start_time=datetime.now(timezone.utc)
            )
            return run_id
        except Exception as e:
            logger.warning(f"[LangSmithTracer] start_trace_request error (fail-open): {e}")
            return None

    def trace_request(self, session_id: str, query: str, messages: list) -> Optional[Any]:
        """Backward compatible trace_request wrapper."""
        run_id = self.start_trace_request(session_id, query, messages)
        if run_id:
            class RunRef:
                def __init__(self, rid):
                    self.id = rid
            return RunRef(run_id)
        return None

    def end_trace_request(
        self,
        run_id: str,
        outputs: Dict[str, Any],
        prompt_tokens: int = 0,
        completion_tokens: int = 0
    ) -> None:
        """Ends and flushes a top-level parent run."""
        if not self.client or not run_id:
            return
        try:
            cost = self.calculate_cost(prompt_tokens, completion_tokens)
            extra = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "estimated_cost_usd": cost
            }
            self.client.update_run(
                run_id=run_id,
                outputs=outputs,
                extra=extra,
                end_time=datetime.now(timezone.utc)
            )
            self.client.flush()
        except Exception as e:
            logger.warning(f"[LangSmithTracer] end_trace_request error (fail-open): {e}")

    def trace_stage_run(
        self,
        name: str,
        run_type: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        parent_run_id: Optional[str] = None,
        duration_seconds: float = 0.0
    ) -> Optional[str]:
        """Creates and immediately completes a pipeline stage child run."""
        if not self.client:
            return None
        try:
            stage_run_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            self.client.create_run(
                id=stage_run_id,
                name=name,
                run_type=run_type,
                inputs=inputs,
                parent_run_id=parent_run_id,
                project_name=self.project_name,
                extra={"duration_seconds": duration_seconds},
                start_time=now
            )
            self.client.update_run(
                run_id=stage_run_id,
                outputs=outputs,
                end_time=now
            )
            self.client.flush()
            return stage_run_id
        except Exception as e:
            logger.warning(f"[LangSmithTracer] trace_stage_run error for '{name}' (fail-open): {e}")
            return None

    def trace_tool_call(self, tool_name: str, args: Dict[str, Any], result: Dict[str, Any], duration_seconds: float) -> None:
        """Logs tool execution details to LangSmith if active."""
        self.trace_stage_run(
            name=f"tool_{tool_name}",
            run_type="tool",
            inputs={"args": args},
            outputs={"result": result},
            duration_seconds=duration_seconds
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Token count estimation (~4 characters per token)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def calculate_cost(prompt_tokens: int, completion_tokens: int) -> float:
        """Calculates estimated USD cost based on token counts."""
        prompt_cost = (prompt_tokens / 1000.0) * COST_PER_1K_PROMPT
        completion_cost = (completion_tokens / 1000.0) * COST_PER_1K_COMPLETION
        return round(prompt_cost + completion_cost, 6)


langsmith_tracer = LangSmithTracer()
