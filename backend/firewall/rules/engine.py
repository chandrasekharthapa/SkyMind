import time
from typing import List, Optional

from backend.firewall.context import RequestContext
from backend.firewall.rules.models import Rule, RuleCondition, PolicyConfig, RuleAction
from backend.firewall.models import FirewallDecision

class RuleEngine:
    """Evaluates RequestContext against a configured PolicyConfig."""
    
    def __init__(self, policy: PolicyConfig):
        self.policy = policy
        # Sort rules by priority descending
        self.rules = sorted(
            [r for r in policy.rules if r.enabled], 
            key=lambda x: x.priority, 
            reverse=True
        )
        
    def evaluate(self, context: RequestContext) -> FirewallDecision:
        start_time = time.time()
        
        matched_rules = []
        skipped_rules = []
        final_action = self.policy.default_action
        decision_reason = "default_policy"
        
        for rule in self.rules:
            if self._evaluate_condition(rule.match, context):
                matched_rules.append(rule.id)
                final_action = rule.action
                decision_reason = f"rule_match:{rule.id}"
                
                context.policy_trace.append({
                    "rule_id": rule.id,
                    "action": rule.action.value,
                    "matched": True
                })
                
                # We stop at the first matching rule, acting as an imperative firewall
                break
            else:
                skipped_rules.append(rule.id)
                context.policy_trace.append({
                    "rule_id": rule.id,
                    "matched": False
                })
                
        is_safe = final_action != RuleAction.BLOCK
        violations = [r.name for r in context.guardrail_results if r.status.value == "UNSAFE"]
        
        decision = FirewallDecision(
            is_safe=is_safe,
            violations=violations,
            details=context.guardrail_results,
            execution_time_ms=(time.time() - start_time) * 1000
        )
        
        return decision

    def _evaluate_condition(self, condition: RuleCondition, context: RequestContext) -> bool:
        """Recursively evaluates a RuleCondition against the RequestContext."""
        
        # Logical AND
        if condition.and_cond is not None:
            return all(self._evaluate_condition(c, context) for c in condition.and_cond)
            
        # Logical OR
        if condition.or_cond is not None:
            return any(self._evaluate_condition(c, context) for c in condition.or_cond)
            
        # Logical NOT
        if condition.not_cond is not None:
            return not self._evaluate_condition(condition.not_cond, context)
            
        # Base property matches
        match = False
        
        # Risk threshold check
        if condition.risk_gt is not None:
            if context.risk_score > condition.risk_gt:
                match = True
        
        # Guardrail result checks
        for res in context.guardrail_results:
            # If guardrail name is specified, it must match
            if condition.guardrail and res.name != condition.guardrail:
                continue
                
            # If verdict is specified, it must match the result's status
            if condition.verdict and res.status.value != condition.verdict:
                continue
                
            # If we reach here and we were looking for a guardrail or verdict, it matched
            if condition.guardrail or condition.verdict:
                match = True
                break
                
        return match
