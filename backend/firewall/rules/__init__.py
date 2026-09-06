from backend.firewall.rules.models import RuleCondition, Rule, RuleAction

# This file exists to ensure pydantic resolves forward references correctly
RuleCondition.model_rebuild()
Rule.model_rebuild()
