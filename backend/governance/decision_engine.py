# Decision engine for SkyMind

"""Implements the Decision Engine using the classification and policy loader.

The engine returns a :class:`DecisionResult` (defined in ``backend/conversation/decision_result.py``)
which drives the rest of the pipeline.
"""

from __future__ import annotations

from typing import Any

from backend.conversation.decision_result import DecisionResult, DecisionActionEnum
from backend.governance.interfaces import DomainClassifier, PolicyLoader, DomainGovernanceEngine
from backend.governance.models import DomainClassification


class DefaultDomainGovernanceEngine(DomainGovernanceEngine):
    """Concrete implementation of the ``DomainGovernanceEngine`` protocol.

    It uses a ``PolicyLoader`` to look up the appropriate action for a given
    ``DomainClassification``. The loader is expected to provide a ``get_action``
    method returning a tuple ``(action: GovernanceActionEnum, metadata: dict)``.
    """

    def __init__(self, policy_loader: PolicyLoader):
        self.policy_loader = policy_loader

    async def decide(self, classification: DomainClassification) -> DecisionResult:
        # The policy loader may be synchronous; we wrap it in ``async`` for the
        # protocol contract.
        action_enum, metadata = self.policy_loader.get_action(
            classification.domain, classification.intent, classification.scope
        )
        # Convert to the ``DecisionActionEnum`` used by the DecisionResult.
        action = DecisionActionEnum(action_enum.value)
        # Build a deterministic result.
        result = DecisionResult(
            action=action,
            continue_pipeline=action == DecisionActionEnum.ALLOW,
            fallback_message=metadata.get("fallback_message"),
            retry_allowed=metadata.get("retry_allowed", False),
            retry_limit=metadata.get("retry_limit", 0),
            reason_code=metadata.get("reason_code"),
            confidence=classification.confidence,
            metadata=metadata,
        )
        return result

__all__ = ["DefaultDomainGovernanceEngine"]
