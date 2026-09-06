"""Domain Governance Engine models.

All Pydantic v2 models required for the Domain Governance pipeline.
They are fully typed and include documentation strings.
"""

from __future__ import annotations

import enum
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field, PositiveFloat


# ---------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------

class DomainEnum(str, enum.Enum):
    """High-level domains relevant to SkyMind."""
    AVIATION = "aviation"
    PERSONAL = "personal"
    EMOTIONAL = "emotional"
    PROGRAMMING = "programming"
    HEALTH = "health"
    ENTERTAINMENT = "entertainment"
    FINANCE = "finance"
    POLITICS = "politics"
    GREETING = "greeting"
    UNKNOWN = "unknown"


class IntentEnum(str, enum.Enum):
    """Fine-grained intents within a domain."""
    FLIGHT_SEARCH = "flight_search"
    PRICE_PREDICTION = "price_prediction"
    BOOKING = "booking"
    GREETING = "greeting"
    THANK_YOU = "thank_you"
    SMALL_TALK = "small_talk"
    EMOTIONAL = "emotional"
    UNKNOWN = "unknown"


class ScopeEnum(str, enum.Enum):
    """Scope classification used by the safety layer."""
    IN_SCOPE = "in_scope"
    SOFT_OFF_TOPIC = "soft_off_topic"
    HARD_OFF_TOPIC = "hard_off_topic"
    SAFETY_OVERRIDE = "safety_override"


class GovernanceActionEnum(str, enum.Enum):
    """Action the governance engine decides the LLM should take."""
    ALLOW = "ALLOW"
    REDIRECT = "REDIRECT"
    LIMIT = "LIMIT"
    REFUSE = "REFUSE"
    SAFETY_OVERRIDE = "SAFETY_OVERRIDE"


# ---------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------

class DomainClassification(BaseModel):
    """Result of the domain-level classifier."""
    domain: DomainEnum = Field(..., description="Detected high-level domain")
    intent: IntentEnum = Field(..., description="Detected user intent")
    scope: ScopeEnum = Field(..., description="Safety scope of the request")
    confidence: PositiveFloat = Field(..., description="Confidence score (0-1)")
    reason_code: str = Field(..., description="Machine-readable reason identifier")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional classifier metadata")


class GovernanceDecision(BaseModel):
    """Decision made by the Domain Governance Engine."""
    domain: DomainEnum
    intent: IntentEnum
    scope: ScopeEnum
    action: GovernanceActionEnum
    confidence: PositiveFloat
    acknowledgement: Optional[str] = None
    redirect_target: Optional[str] = None
    response_style: Optional[str] = None
    prompt_instructions: Optional[str] = None
    validator_rules: Optional[List[str]] = None
    trace: Optional["GovernanceTrace"] = None
    metadata: Optional[Dict[str, Any]] = None


class GovernanceTrace(BaseModel):
    """Telemetry trace used for observability and debugging."""
    request_id: str
    classifications: List[DomainClassification] = Field(default_factory=list)
    decision: Optional[GovernanceDecision] = None
    timestamps: List[float] = Field(default_factory=list)
    trace_id: Optional[str] = None

    class Config:
        json_encoders = {float: lambda v: round(v, 3)}

    def add_classification(self, classification: DomainClassification, ts_ms: float) -> None:
        self.classifications.append(classification)
        self.timestamps.append(ts_ms)

    def set_decision(self, decision: GovernanceDecision, ts_ms: float) -> None:
        self.decision = decision
        self.timestamps.append(ts_ms)


class PromptContext(BaseModel):
    """Aggregated context passed to the PromptComposer."""
    history: List[Dict[str, Any]]
    decision: GovernanceDecision
    tool_context: Optional[Dict[str, Any]] = None
    safety_context: Optional[Dict[str, Any]] = None
    retrieval_context: Optional[Dict[str, Any]] = None
    system_instructions: List[str] = Field(default_factory=list)


class ViolationSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ViolationCode(str, enum.Enum):
    BANNED_PHRASE = "BANNED_PHRASE"
    DOMAIN_DRIFT = "DOMAIN_DRIFT"
    PERSONAL_FOLLOWUP = "PERSONAL_FOLLOWUP"
    THERAPIST_BEHAVIOR = "THERAPIST_BEHAVIOR"
    PROGRAMMING_RESPONSE = "PROGRAMMING_RESPONSE"
    FINANCIAL_ADVICE = "FINANCIAL_ADVICE"
    POLITICAL_RESPONSE = "POLITICAL_RESPONSE"


class Violation(BaseModel):
    code: ViolationCode
    message: str
    severity: ViolationSeverity


class ValidationResult(BaseModel):
    passed: bool
    violations: List[Violation] = Field(default_factory=list)
    severity: ViolationSeverity = ViolationSeverity.LOW
    regeneration_required: bool = False


__all__ = [
    "DomainEnum",
    "IntentEnum",
    "ScopeEnum",
    "GovernanceActionEnum",
    "DomainClassification",
    "GovernanceDecision",
    "GovernanceTrace",
    "PromptContext",
    "ViolationSeverity",
    "ViolationCode",
    "Violation",
    "ValidationResult",
]
