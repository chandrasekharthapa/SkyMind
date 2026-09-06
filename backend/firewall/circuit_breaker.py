import time
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failing, failing fast
    HALF_OPEN = "HALF_OPEN" # Testing recovery

class CircuitBreaker:
    """
    Implements a circuit breaker pattern to prevent cascading failures 
    when external services (like NVIDIA APIs) go down.
    """
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        
    def record_success(self):
        """Called when a call succeeds. Resets the circuit if HALF_OPEN."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker recovered, transitioning to CLOSED.")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        
    def record_failure(self):
        """Called when a call fails. Trips the circuit if threshold reached."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            logger.error(f"Circuit breaker tripped! Transitioning to OPEN state.")
            self.state = CircuitState.OPEN
            
    def can_execute(self) -> bool:
        """Determines if a call should be allowed to execute."""
        if self.state == CircuitState.CLOSED:
            return True
            
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info("Circuit breaker recovery timeout passed, transitioning to HALF_OPEN.")
                self.state = CircuitState.HALF_OPEN
                return True
            return False
            
        if self.state == CircuitState.HALF_OPEN:
            # Allow only one test request
            return True
            
        return False
