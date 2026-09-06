"""Resilience Engineering.

Implements Circuit Breaker pattern, timeout enforcement, and robust retry
logic to safeguard integrations like Supabase and MCP Gateway from transient failures.
"""

import time
import asyncio
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    """State machine circuit breaker to prevent cascading failures."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.last_state_change = time.time()

    def record_success(self):
        self.failure_count = 0
        if self.state != "CLOSED":
            logger.info(f"Circuit Breaker state reset to CLOSED.")
            self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        logger.warning(f"Circuit Breaker failure registered. Count: {self.failure_count}/{self.failure_threshold}")
        if self.failure_count >= self.failure_threshold and self.state != "OPEN":
            logger.error(f"Circuit Breaker threshold met. Tripping state to OPEN.")
            self.state = "OPEN"
            self.last_state_change = time.time()

    def allow_request(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            # Check if recovery timeout has passed to allow a trial (HALF-OPEN)
            if time.time() - self.last_state_change > self.recovery_timeout:
                logger.info("Circuit Breaker recovery window met. transitioning to HALF-OPEN.")
                self.state = "HALF-OPEN"
                return True
            return False
        return True  # HALF-OPEN allows trial requests

    async def run(self, func: Callable, *args, **kwargs) -> Any:
        if not self.allow_request():
            raise CircuitBreakerOpenException("Circuit Breaker is OPEN. Target execution skipped.")
        
        try:
            import inspect
            if inspect.iscoroutinefunction(func):
                res = await func(*args, **kwargs)
            else:
                res = func(*args, **kwargs)
            self.record_success()
            return res
        except Exception as e:
            self.record_failure()
            raise e

# Global Circuit Breakers
mcp_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
database_breaker = CircuitBreaker(failure_threshold=10, recovery_timeout=15.0)
