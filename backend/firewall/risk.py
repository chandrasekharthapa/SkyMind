from typing import Dict, Any
from backend.firewall.context import RequestContext
from backend.firewall.models import GuardrailStatus

class RiskEngine:
    """
    Calculates a cumulative risk score based on guardrail violations.
    Supports configuring weights per guardrail type.
    """
    
    def __init__(self, weights: Dict[str, float] = None, strategy: str = "max"):
        # Default enterprise risk weights if none provided
        self.weights = weights or {
            "jailbreak-detect": 100.0,
            "content-safety": 90.0,
            "topic-control": 40.0
        }
        self.strategy = strategy

    def calculate(self, context: RequestContext) -> float:
        """Calculates risk score based on the context's guardrail results."""
        if not context.guardrail_results:
            return 0.0
            
        scores = []
        for result in context.guardrail_results:
            if result.status == GuardrailStatus.UNSAFE:
                # Get the weight for this guardrail, default to 50 if unknown
                score = self.weights.get(result.name, 50.0)
                scores.append(score)
                
        if not scores:
            return 0.0
            
        if self.strategy == "max":
            return max(scores)
        elif self.strategy == "sum":
            return sum(scores)
        elif self.strategy == "average":
            return sum(scores) / len(scores)
            
        return max(scores)
