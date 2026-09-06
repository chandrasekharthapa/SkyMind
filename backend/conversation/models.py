'''Conversation Governance Engine data models.

These models define the structures used by the Conversation Governance Engine to
classify incoming user messages, decide on an appropriate action, and keep a trace
of how the decision was reached throughout the pipeline.

The system uses Pydantic v2 and is fully type‑annotated to support static analysis
and IDE assistance.
'''

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, PositiveFloat, conlist


class IntentEnum(str, Enum):
    """High‑level intents recognized by the conversation classifier."""
    PERSONAL = "personal"  # e.g., "my girlfriend", "how are you"
    TECHNICAL = "technical"  # domain‑specific questions
    OFFTOPIC = "offtopic"  # unrelated to aviation
    UNKNOWN = "unknown"


class ConversationClassification(BaseModel):
    """Result of the intent classification stage.

    Attributes
    ----------
    intent: IntentEnum
        The high‑level intent inferred from the user message.
    domain: str
        The target domain (e.g., ``"aviation"``).  This helps the engine enforce that
        the conversation stays within the product scope.
    scope: str
        A free‑form description of the conversation scope (e.g., ``"personal"``
        or ``"flight‑operations"``).
    confidence: PositiveFloat
        Confidence score (0‒1) of the classification model.
    suggested_action: Optional[str]
        Optional hint for the next pipeline stage, such as ``"redirect_to_aviation"``.
    """

    intent: IntentEnum = Field(..., description="Inferred user intent")
    domain: str = Field(..., description="Target domain for the conversation")
    scope: str = Field(..., description="Scope or topic of the message")
    confidence: PositiveFloat = Field(..., description="Confidence of the classification (0‑1)")
    suggested_action: Optional[str] = Field(
        None, description="Optional suggestion for the next processing step"
    )


class DecisionActionEnum(str, Enum):
    """Possible actions the engine can take after classification."""
    ALLOW = "allow"  # Proceed with normal LLM response
    DENY = "deny"  # Block the request entirely
    REDIRECT = "redirect"  # Politely steer back to aviation topic
    ACKNOWLEDGE = "acknowledge"  # Simple acknowledgement without detailed answer


class ConversationDecision(BaseModel):
    """Final decision emitted by the Conversation Governance Engine.

    Attributes
    ----------
    action: DecisionActionEnum
        The action to be performed by the downstream LLM handler.
    acknowledgement: Optional[str]
        Human‑readable message that will be sent back to the user when the
        ``ACKNOWLEDGE`` or ``REDIRECT`` actions are chosen.
    redirect_target: Optional[str]
        When ``action`` is ``REDIRECT``, this field can contain a topic or a
        prompt fragment that the LLM should use to steer the conversation.
    metadata: Optional[Dict[str, Any]]
        Additional opaque data useful for logging or downstream extensions.
    """

    action: DecisionActionEnum = Field(..., description="Engine‑determined action")
    acknowledgement: Optional[str] = Field(
        None, description="Message to return to the user if applicable"
    )
    redirect_target: Optional[str] = Field(
        None, description="Target topic or prompt fragment for redirection"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Arbitrary metadata for extensibility"
    )


class ConversationTrace(BaseModel):
    """Trace of a single request through the conversation governance pipeline.

    It records every classification produced and the final decision, together
    with timestamps so that observability tools can visualise the flow.
    """

    request_id: str = Field(..., description="Unique identifier for the request")
    classifications: List[ConversationClassification] = Field(
        default_factory=list,
        description="All classification results produced by the pipeline",
    )
    decision: ConversationDecision = Field(..., description="Final decision for the request")
    timestamps: List[float] = Field(
        default_factory=list,
        description="Monotonic timestamps (ms) recorded at each pipeline stage",
    )
    trace_id: Optional[str] = Field(
        None, description="Optional OpenTelemetry trace identifier for correlation"
    )

    class Config:
        orm_mode = True
        json_encoders = {float: lambda v: round(v, 3)}

    def add_classification(self, classification: ConversationClassification, timestamp_ms: float) -> None:
        """Append a classification result and its timestamp to the trace."""
        self.classifications.append(classification)
        self.timestamps.append(timestamp_ms)

    def set_decision(self, decision: ConversationDecision, timestamp_ms: float) -> None:
        """Set the final decision and record the time it was made."""
        self.decision = decision
        self.timestamps.append(timestamp_ms)

