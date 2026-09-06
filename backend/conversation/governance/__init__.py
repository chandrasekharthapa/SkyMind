'''Conversation Governance package.

Provides a thin wrapper that ties together the DomainClassifier,
Policy loader, and simple governance decision logic.
'''

from __future__ import annotations

from typing import List, Dict, Any

from backend.governance.classifier import classify_message
from backend.governance.engine import GovernancePolicyLoader
from backend.governance.models import (
    DomainClassification,
    GovernanceDecision,
    GovernanceActionEnum,
)

# Export the enum under the name expected by the router
DecisionActionEnum = GovernanceActionEnum

_policy_loader = GovernancePolicyLoader()

def evaluate_conversation(messages: List[Dict[str, Any]], request_id: str) -> GovernanceDecision:
    """Evaluate the conversation and return a governance decision.

    *messages* – List of message dicts (role/content) from the chat request.
    *request_id* – Identifier propagated from the request context for tracing.

    The function runs a simple pipeline:
    1. Classify the latest user message (or the concatenated user text).
    2. Look up the domain policy for the classification domain.
    3. Build a :class:`GovernanceDecision` with the appropriate action and
       acknowledgement/redirect information.
    """
    if not messages:
        raise ValueError("No messages provided for governance evaluation")
    # Extract the latest user message text
    user_text = " ".join(msg["content"] for msg in messages if msg.get("role") == "user")
    classification: DomainClassification = classify_message(user_text)
    # Load policy action for the detected domain
    decision: GovernanceDecision = policy_loader.get_action(classification.domain.value)
    # Populate additional fields from classification
    decision.domain = classification.domain
    decision.intent = classification.intent
    decision.scope = classification.scope
    decision.confidence = classification.confidence
    return decision

__all__ = ["evaluate_conversation", "DecisionActionEnum", "policy_loader"]

