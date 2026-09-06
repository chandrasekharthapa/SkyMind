'''Interfaces for the Domain Governance subsystem.'''

from __future__ import annotations

from typing import Protocol, List, Dict, Any

from ..models import (
    DomainClassification,
    GovernanceDecision,
    PromptContext,
    ValidationResult,
)

# ---------------------------------------------------------------------
# Domain Classifier
# ---------------------------------------------------------------------

class DomainClassifier(Protocol):
    async def classify(self, messages: List[Dict[str, Any]]) -> DomainClassification: ...

# ---------------------------------------------------------------------
# Policy Loader
# ---------------------------------------------------------------------

class PolicyLoader(Protocol):
    def get_policy(self) -> "GovernancePolicy": ...
    def source_identifier(self) -> str: ...

# ---------------------------------------------------------------------
# Governance Engine
# ---------------------------------------------------------------------

class DomainGovernanceEngine(Protocol):
    async def decide(self, classification: DomainClassification) -> GovernanceDecision: ...

# ---------------------------------------------------------------------
# Prompt Composer
# ---------------------------------------------------------------------

class PromptComposer(Protocol):
    def render(self, decision: GovernanceDecision, history: List[Dict[str, Any]]) -> str: ...
    def render_with_adjustments(
        self,
        decision: GovernanceDecision,
        history: List[Dict[str, Any]],
        validation_result: ValidationResult,
    ) -> str: ...

# ---------------------------------------------------------------------
# Response Validator
# ---------------------------------------------------------------------

class ResponseValidator(Protocol):
    async def validate(self, response: str, decision: GovernanceDecision) -> ValidationResult: ...

# ---------------------------------------------------------------------
# Brand Identity Policy
# ---------------------------------------------------------------------

class BrandIdentityPolicy(Protocol):
    def is_banned_phrase(self, phrase: str) -> bool: ...
    def tone_descriptors(self) -> List[str]: ...

__all__ = [
    "DomainClassifier",
    "PolicyLoader",
    "DomainGovernanceEngine",
    "PromptComposer",
    "ResponseValidator",
    "BrandIdentityPolicy",
]
