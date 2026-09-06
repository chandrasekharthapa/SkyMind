import time
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from backend.firewall.models import GuardrailResult, GuardrailStatus
from backend.firewall.config import FirewallConfig
from backend.firewall.exceptions import FirewallTimeoutError, GuardrailExecutionError

logger = logging.getLogger(__name__)

class BaseGuardrail(ABC):
    """Abstract base class for all guardrails."""
    
    name: str = "base-guardrail"
    
    def __init__(self, config: FirewallConfig):
        self.config = config
        
    @abstractmethod
    async def _execute(self, prompt: str) -> GuardrailResult:
        """Internal execution logic to be implemented by subclasses."""
        pass
        
    async def evaluate(self, prompt: str) -> GuardrailResult:
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
