from typing import List
from .models import GuardrailResult, FirewallDecision, GuardrailStatus
from .config import FirewallConfig

class PolicyEngine:
    """Evaluates the collection of GuardrailResults to form a final FirewallDecision."""
    
    def __init__(self, config: FirewallConfig):
        self.config = config
        
    def evaluate(self, results: List[GuardrailResult], execution_time_ms: float) -> FirewallDecision:
        violations = []
        is_safe = True
        
        for result in results:
            if result.status == GuardrailStatus.UNSAFE:
                violations.append(result.name)
                is_safe = False
            elif result.status == GuardrailStatus.ERROR:
                if not self.config.fail_open:
                    violations.append(result.name)
                    is_safe = False
            elif result.status == GuardrailStatus.UNKNOWN:
                if not self.config.fail_open:
                    violations.append(result.name)
                    is_safe = False
                    
        return FirewallDecision(
            is_safe=is_safe,
            violations=violations,
            details=results,
            execution_time_ms=execution_time_ms
        )
