'''Governance Policy model.

This file defines the data structure for the governance policy loaded from YAML.
'''

from __future__ import annotations

from typing import Dict, Tuple, Any

from pydantic import BaseModel, Field

from .models import DomainEnum, IntentEnum, ScopeEnum, GovernanceActionEnum


class GovernancePolicy(BaseModel):
    """Immutable mapping from (domain, intent, scope) to action and metadata.

    The policy is loaded from a YAML file and cached for fast lookup.
    """
    policy_map: Dict[Tuple[DomainEnum, IntentEnum, ScopeEnum], Dict[str, Any]] = Field(default_factory=dict)

    def get_action(self, domain: DomainEnum, intent: IntentEnum, scope: ScopeEnum) -> Tuple[GovernanceActionEnum, Dict[str, Any]]:
        """Return the action and associated metadata for the given keys.

        Falls back in the order defined in the implementation plan.
        """
        # Exact match
        key = (domain, intent, scope)
        if key in self.policy_map:
            entry = self.policy_map[key]
            return GovernanceActionEnum(entry["action"]), entry.get("metadata", {})
        # Fallback to (domain, intent, IN_SCOPE)
        key = (domain, intent, ScopeEnum.IN_SCOPE)
        if key in self.policy_map:
            entry = self.policy_map[key]
            return GovernanceActionEnum(entry["action"]), entry.get("metadata", {})
        # Fallback to (domain, UNKNOWN, *)
        key = (domain, IntentEnum.UNKNOWN, scope)
        if key in self.policy_map:
            entry = self.policy_map[key]
            return GovernanceActionEnum(entry["action"]), entry.get("metadata", {})
        # Default REFUSE
        return GovernanceActionEnum.REFUSE, {}

    class Config:
        allow_mutation = False
        arbitrary_types_allowed = True

__all__ = ["GovernancePolicy"]
