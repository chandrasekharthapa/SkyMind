import time
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from backend.firewall.models import GuardrailResult, GuardrailStatus
from backend.firewall.config import FirewallConfig
from backend.firewall.exceptions import FirewallTimeoutError, GuardrailExecutionError
from backend.firewall.circuit_breaker import CircuitBreaker, CircuitState

logger = logging.getLogger(__name__)

class BaseGuardrail(ABC):
    """Abstract base class for all guardrails."""
    
    name: str = "base-guardrail"
    
    def __init__(self, config: FirewallConfig):
        self.config = config
        self.breaker = CircuitBreaker(
            failure_threshold=max(1, config.breaker_threshold),
            recovery_timeout=config.breaker_recovery_seconds,
        )
        
    @abstractmethod
    async def _execute(self, prompt: str) -> GuardrailResult:
        """Internal execution logic to be implemented by subclasses."""
        pass
        
    async def evaluate(self, prompt: str) -> GuardrailResult:
        """Runs the check behind the circuit breaker: a guardrail that keeps
        failing is skipped for a while instead of adding its timeout to every
        request. The result is ERROR either way, so fail_open decides."""
        if not self.breaker.can_execute():
            return GuardrailResult(
                name=self.name,
                status=GuardrailStatus.ERROR,
                raw_response="",
                latency_ms=0.0,
                error="skipped: failing repeatedly, retrying later",
            )
        result = await self._evaluate_once(prompt)
        if result.status == GuardrailStatus.ERROR:
            self.breaker.record_failure()
            if self.breaker.state == CircuitState.OPEN:
                logger.error(
                    f"Guardrail {self.name} keeps failing ({result.error}); "
                    f"skipping it for {self.config.breaker_recovery_seconds:.0f}s.")
        else:
            self.breaker.record_success()
        return result

    async def _evaluate_once(self, prompt: str) -> GuardrailResult:
        """Wraps execution with retries, timeouts, and latency measurement."""
        start_time = time.time()
        
        try:
            # Wrap the retrying loop inside asyncio.wait_for for total timeout control
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.config.retry_count),
                wait=wait_exponential(multiplier=self.config.retry_backoff),
                reraise=True
            ):
                with attempt:
                    result = await asyncio.wait_for(
                        self._execute(prompt), 
                        timeout=self.config.timeout
                    )
                    
                    latency = (time.time() - start_time) * 1000
                    result.latency_ms = latency
                    return result
                    
        except asyncio.TimeoutError:
            latency = (time.time() - start_time) * 1000
            logger.error(f"Guardrail {self.name} timed out after {self.config.timeout}s")
            return GuardrailResult(
                name=self.name,
                status=GuardrailStatus.ERROR,
                raw_response="",
                latency_ms=latency,
                error="TimeoutError"
            )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error(f"Guardrail {self.name} failed: {e}")
            return GuardrailResult(
                name=self.name,
                status=GuardrailStatus.ERROR,
                raw_response="",
                latency_ms=latency,
                error=str(e)
            )
