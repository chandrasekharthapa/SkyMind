'''Conversation Governance Engine core logic.

This module provides a simple, rule‑based implementation of the
Conversation Governance Engine. It classifies user intent, decides on an
action, and records a trace that can be emitted to OpenTelemetry or audit
services.

In a production system the classification would be driven by a ML model,
but for the purposes of this exercise we implement a lightweight keyword
based approach that satisfies the requirement of preventing personal
conversations.
'''

from __future__ import annotations

import re
import time
import uuid
from typing import List, Dict, Any

from .models import (
    IntentEnum,
    DecisionActionEnum,
    ConversationClassification,
    ConversationDecision,
    ConversationTrace,
)

# Simple keyword sets for demonstration.  In a real system these would be
# replaced by a trained classifier.
_PERSONAL_KEYWORDS = {
    "girlfriend", "boyfriend", "my gf", "my bf", "my partner", "relationship",
    "love", "date", "married", "husband", "wife", "family", "personal"
}

_DEFENSIVE_ACK = "I’m here to help with aviation‑related questions. How can I assist you with flight data or operations?"


def _detect_personal(text: str) -> bool:
    """Return True if any personal keyword is found in *text*.

    The check is case‑insensitive and looks for whole words.
    """
    lowered = text.lower()
    # Use regex word boundaries to avoid matching substrings inside other words.
    for kw in _personal_keywords():
        if re.search(r"\b" + re.escape(kw) + r"\b", lowered):
            return True
    return False


def _personal_keywords() -> set[str]:
    """Return a copy of the personal keyword set for testability."""
    return set(_PERSONAL_KEYWORDS)


def classify_message(text: str) -> ConversationClassification:
    """Classify *text* into a :class:`ConversationClassification`.

    Currently the implementation is rule‑based:

    * If personal keywords are detected → intent ``PERSONAL`` and domain
      ``aviation`` with low confidence.
    * Otherwise → intent ``TECHNICAL`` with high confidence.

    The ``suggested_action`` hint is used by the decision stage.
    """
    is_personal = _detect_personal(text)
    if is_personal:
        intent = IntentEnum.PERSONAL
        confidence = 0.92  # Arbitrary high confidence for rule‑based detection
        suggested = "redirect_to_aviation"
    else:
        intent = IntentEnum.TECHNICAL
        confidence = 0.95
        suggested = None
    return ConversationClassification(
        intent=intent,
        domain="aviation",
        scope="personal" if is_personal else "technical",
        confidence=confidence,
        suggested_action=suggested,
    )


def decide(classification: ConversationClassification) -> ConversationDecision:
    """Derive a :class:`ConversationDecision` from a classification result.

    * Personal intent → ``REDIRECT`` with a polite acknowledgement.
    * Technical intent → ``ALLOW``.
    """
    if classification.intent == IntentEnum.PERSONAL:
        return ConversationDecision(
            action=DecisionActionEnum.REDIRECT,
            acknowledgement=_DEFENSIVE_ACK,
            redirect_target="aviation",
        )
    else:
        return ConversationDecision(action=DecisionActionEnum.ALLOW)


def evaluate_conversation(messages: List[Dict[str, Any]], request_id: str) -> ConversationTrace:
    """Run the full Conversation Governance pipeline for a list of messages.

    * ``messages`` – list of dicts with ``role``/``content`` as used by the
      chat endpoint.
    * ``request_id`` – identifier that ties the trace to the request.

    Returns a :class:`ConversationTrace` containing the classification and
    the final decision.  The trace can later be emitted to OpenTelemetry or
    persisted for auditing.
    """
    # Concatenate user messages for classification.  The firewall already
    # normalised the prompt, but we operate on the raw text here.
    user_text = " ".join(msg.get("content", "") for msg in messages if msg.get("role") == "user")
    classification = classify_message(user_text)
    decision = decide(classification)
    trace = ConversationTrace(
        request_id=request_id,
        classifications=[classification],
        decision=decision,
        timestamps=[time.time() * 1000],
    )
    return trace


# Exported symbols for external import
__all__ = [
    "ConversationTrace",
    "ConversationClassification",
    "ConversationDecision",
    "evaluate_conversation",
    "classify_message",
    "decide",
]

