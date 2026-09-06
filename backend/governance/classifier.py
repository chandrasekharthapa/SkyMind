"""Domain classifier for SkyMind.

A lightweight rule-based classifier that maps incoming user messages to a
DomainEnum, IntentEnum, ScopeEnum, and provides a confidence score.
"""

from __future__ import annotations

import re
from typing import List, Dict

from .models import (
    DomainEnum,
    IntentEnum,
    ScopeEnum,
    DomainClassification,
)


# Keyword tables for each domain. All entries are lower-case.
_KEYWORD_MAP: Dict[DomainEnum, List[str]] = {
    DomainEnum.AVIATION: [
        "flight", "aviation", "airline", "airport", "baggage", "runway",
        "aircraft", "regulation", "flight schedule", "flight analytics",
        "flight price", "price prediction", "airfare", "boarding",
        "departure", "arrival", "terminal", "check-in", "layover",
        "connecting flight", "ticket", "travel", "destination",
        "turbulence", "pilot", "cabin", "jet", "airplane", "fly", "flying",
        "book", "booking", "trend", "trends", "route", "routes",
    ],
    DomainEnum.PERSONAL: [
        "girlfriend", "boyfriend", "relationship", "love", "love you",
        "my partner", "dating", "married", "husband", "wife",
        "crush", "breakup", "broke up",
    ],
    DomainEnum.EMOTIONAL: [
        "sad", "stressed", "lonely", "depressed", "unhappy",
        "anxious", "worried", "crying", "heartbroken", "miserable",
        "feeling down", "feeling low", "i feel bad",
    ],
    DomainEnum.ENTERTAINMENT: [
        "joke", "movie", "music", "song", "game", "netflix",
        "spotify", "anime", "manga", "meme",
    ],
    DomainEnum.PROGRAMMING: [
        "code", "python", "javascript", "java", "algorithm",
        "programming", "debug", "compile", "api", "database",
        "sql", "react", "html", "css", "git",
    ],
    DomainEnum.FINANCE: [
        "stock", "investment", "bank", "loan", "crypto",
        "bitcoin", "trading", "mutual fund", "portfolio", "finance",
    ],
    DomainEnum.HEALTH: [
        "health", "medicine", "doctor", "symptom", "disease",
        "hospital", "prescription", "therapy", "diagnosis",
    ],
    DomainEnum.POLITICS: [
        "election", "president", "policy", "government",
        "political", "congress", "parliament", "vote", "modi",
        "minister", "politician", "trump", "biden", "obama", "politics",
    ],
}

# Scope determination based on domain
_SCOPE_FOR_DOMAIN: Dict[DomainEnum, ScopeEnum] = {
    DomainEnum.PERSONAL: ScopeEnum.SOFT_OFF_TOPIC,
    DomainEnum.EMOTIONAL: ScopeEnum.SOFT_OFF_TOPIC,
    DomainEnum.ENTERTAINMENT: ScopeEnum.HARD_OFF_TOPIC,
    DomainEnum.PROGRAMMING: ScopeEnum.HARD_OFF_TOPIC,
    DomainEnum.FINANCE: ScopeEnum.HARD_OFF_TOPIC,
    DomainEnum.HEALTH: ScopeEnum.HARD_OFF_TOPIC,
    DomainEnum.POLITICS: ScopeEnum.HARD_OFF_TOPIC,
    DomainEnum.AVIATION: ScopeEnum.IN_SCOPE,
    DomainEnum.GREETING: ScopeEnum.IN_SCOPE,
    DomainEnum.UNKNOWN: ScopeEnum.HARD_OFF_TOPIC,
}


def _match_keywords(text: str, keywords: List[str]) -> bool:
    """Check if any keyword matches in the text using word-start boundary.

    Uses ``\\b`` at the start to anchor to a word boundary, but allows
    the keyword to appear as a prefix of a longer word (e.g., ``flight``
    matches ``flights``).
    """
    lowered = text.lower()
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw), lowered):
            return True
    return False


# Greeting keywords — these are ALLOWED through to the LLM.
_GREETING_KEYWORDS = [
    "hello", "hi", "hey", "good morning", "good afternoon",
    "good evening", "howdy", "greetings", "thanks", "thank you",
    "bye", "goodbye", "see you",
]


def classify_message(text: str) -> DomainClassification:
    """Return a DomainClassification for the given text.

    Iterates over the keyword map in a deterministic order and picks
    the first matching domain. Aviation is checked LAST so that
    off-topic domains take priority (preventing "I love my flight
    to Goa" from being classified as personal).

    Priority order: emotional > personal > entertainment > programming >
    finance > health > politics > aviation > unknown.
    """
    # Check non-aviation domains first (off-topic detection takes priority)
    priority_order = [
        DomainEnum.EMOTIONAL,
        DomainEnum.PERSONAL,
        DomainEnum.ENTERTAINMENT,
        DomainEnum.PROGRAMMING,
        DomainEnum.FINANCE,
        DomainEnum.HEALTH,
        DomainEnum.POLITICS,
    ]

    for domain in priority_order:
        keywords = _KEYWORD_MAP.get(domain, [])
        if _match_keywords(text, keywords):
            # Special case: if both aviation AND off-topic keywords are
            # present, aviation wins (e.g. "I'm sad my flight got cancelled")
            aviation_keywords = _KEYWORD_MAP.get(DomainEnum.AVIATION, [])
            if _match_keywords(text, aviation_keywords):
                break  # Fall through to aviation check below

            scope = _SCOPE_FOR_DOMAIN.get(domain, ScopeEnum.HARD_OFF_TOPIC)
            return DomainClassification(
                domain=domain,
                intent=IntentEnum.UNKNOWN,
                scope=scope,
                confidence=0.92,
                reason_code="keyword_match",
                metadata={"matched_domain": domain.value},
            )

    # Check aviation
    aviation_keywords = _KEYWORD_MAP.get(DomainEnum.AVIATION, [])
    if _match_keywords(text, aviation_keywords):
        return DomainClassification(
            domain=DomainEnum.AVIATION,
            intent=IntentEnum.UNKNOWN,
            scope=ScopeEnum.IN_SCOPE,
            confidence=0.95,
            reason_code="keyword_match",
            metadata={"matched_domain": "aviation"},
        )

    # Check greetings — these are allowed through to the LLM as DomainEnum.GREETING
    if _match_keywords(text, _GREETING_KEYWORDS):
        return DomainClassification(
            domain=DomainEnum.GREETING,
            intent=IntentEnum.GREETING,
            scope=ScopeEnum.IN_SCOPE,
            confidence=0.90,
            reason_code="greeting",
            metadata={"matched_domain": "greeting"},
        )

    # No match -> UNKNOWN
    return DomainClassification(
        domain=DomainEnum.UNKNOWN,
        intent=IntentEnum.UNKNOWN,
        scope=ScopeEnum.HARD_OFF_TOPIC,
        confidence=0.5,
        reason_code="no_match",
        metadata=None,
    )


__all__ = ["classify_message", "DomainClassification"]


