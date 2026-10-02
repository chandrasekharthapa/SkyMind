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
    # Strong aviation words: unambiguous on their own, and they win over an
    # off-topic keyword in the same message ("I'm sad my flight got cancelled").
    # Everyday travel words live in _WEAK_AVIATION_KEYWORDS below.
    DomainEnum.AVIATION: [
        "flight", "aviation", "airline", "airport", "baggage", "runway",
        "aircraft", "flight schedule", "flight analytics",
        "flight price", "price prediction", "airfare", "boarding",
        "departure", "arrival", "terminal", "check-in", "layover",
        "connecting flight", 
        "turbulence", "pilot", "cabin", "jet", "airplane", "fly", "flying",
        
        # The words people actually use to ask about fares. None of these were
        # here, so "Delhi to Mumbai price on Friday" or "cheapest fare to Goa"
        # matched nothing, fell through to UNKNOWN, and were redirected with
        # "I'm designed to assist with aviation and travel" — the product's core
        # question refused by its own scope filter.
        "fare", "fares", 
        
        "itinerary", "one way", "one-way", "oneway",
        "round trip", "return trip", "nonstop", "non-stop", 
        "stopover", "business class", "first class", "premium economy",
        "pnr", 
        
        "indigo", "air india", "vistara", "spicejet", "akasa", "airasia",
        "go first", "alliance air", "star air",
        # General air-travel questions the assistant answers from knowledge:
        # "why do my ears pop on takeoff?", "can I carry a power bank?", "what
        # ID do I need for a domestic flight?". None of these words were here,
        # so the questions were redirected as off-topic.
        "plane", "planes", "takeoff", "take-off", "take off", "cockpit",
        "air hostess", "flight attendant", "jet lag", "jetlag", "visa",
        "passport", "security check", "immigration", "lounge",
        "duty free", "duty-free", "carry-on", "carry on", "cabin bag", 
        "check-in bag", "power bank", "boarding pass", "web check",
        "digi yatra", "digiyatra", "dgca", "air traffic", "altitude",
        "autopilot", "boeing", "airbus", "a320", "a321", "737", "787",
        "emergency exit", "window seat", "aisle", "legroom", 
        "frequent flyer", "air miles", "cancelled", "canceled",
        "missed connection", "excess baggage",
        "unaccompanied minor", "pet travel", "in-flight",
        "inflight", "economy class", "red-eye", "codeshare", "tarmac",
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
        # "policy" was here, which sent "IndiGo's cancellation policy" — a booking
        # question — to the politics redirect ("can't discuss politics").
        "election", "president", "government",
        "political", "congress", "parliament", "vote", "modi",
        "minister", "politician", "trump", "biden", "obama", "politics",
    ],
}

# Weak aviation words: travel-flavoured but also everyday words ("price",
# "cheap", "trip", "ticket", "delay"). They make a message aviation only when
# nothing off-topic is present. As strong words they let "what's the bitcoin
# price?" or "movie ticket prices" win over the finance/entertainment redirect.
_WEAK_AVIATION_KEYWORDS: List[str] = [
    "price", "prices", "pricing", "cheap", "cheapest", "cost", "costs", "expensive",
    "deal", "deals", "trip", "trips", "holiday", "vacation", "direct", "seat", "seats",
    "forecast", "predict", "prediction", "depart", "leave", "arrive", "delay",
    "delayed", "connection", "transit", "upgrade", "crew", "landing", "customs",
    "trend", "trends", "book", "booking", "ticket", "destination", "route", "routes",
    "regulation", "refund", "cancellation", "reschedule", "travel", "economy",
    "hand bag", "liquids", "infant", "wheelchair", "atc",
]

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
    matches ``flights``). Used for aviation, where prefix matching is what
    lets one entry cover flights/flying/booked.
    """
    lowered = text.lower()
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw), lowered):
            return True
    return False


def _match_whole_words(text: str, keywords: List[str]) -> bool:
    """Whole-word match (allowing a plural s/es), for the off-topic domains.

    Prefix matching is wrong for a deny-list: "stock" matched "Stockholm",
    "sad" matched "saddle", "code" matched "codeshare", "api" matched "apiece",
    and each of those redirected a travel question away from the assistant.
    """
    lowered = text.lower()
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"(?:s|es)?\b", lowered):
            return True
    return False


# Indian airport codes and the city names people type for them. A message naming
# a route ("DEL to BOM tomorrow", "Bangalore to Goa") is an aviation question even
# with no aviation word in it. Codes are matched only when written in capitals in
# the original text, because several are ordinary English words in lower case.
_AIRPORT_CODES = {
    "DEL", "BOM", "BLR", "MAA", "CCU", "HYD", "GOI", "GOX", "COK", "BBI", "AMD",
    "PNQ", "JAI", "LKO", "PAT", "GAU", "IXC", "SXR", "TRV", "VNS", "IXB", "NAG",
    "IDR", "BHO", "RPR", "VTZ", "IXR", "CJB", "IXM", "TRZ", "IXE", "ATQ", "DED",
    "IXZ", "STV", "UDR", "IXJ", "IXL", "DIB", "IMF", "AGR", "GAY", "VGA", "TIR",
}
_CITY_NAMES = [
    "delhi", "new delhi", "mumbai", "bombay", "bangalore", "bengaluru", "chennai",
    "madras", "kolkata", "calcutta", "hyderabad", "goa", "kochi", "cochin",
    "bhubaneswar", "ahmedabad", "pune", "jaipur", "lucknow", "patna", "guwahati",
    "chandigarh", "srinagar", "thiruvananthapuram", "trivandrum", "varanasi",
    "bagdogra", "nagpur", "indore", "bhopal", "raipur", "visakhapatnam", "vizag",
    "ranchi", "coimbatore", "madurai", "mangalore", "amritsar", "dehradun",
    "port blair", "surat", "udaipur", "jammu", "leh", "dibrugarh", "imphal",
]


_ROUTE_CODES = re.compile(r"\b([a-z]{3})\s*(?:to|-|->|→|–)\s*([a-z]{3})\b", re.IGNORECASE)


def _mentions_airport(text: str) -> bool:
    if any(tok in _AIRPORT_CODES for tok in re.findall(r"\b[A-Z]{3}\b", text)):
        return True
    # "del to bom": codes typed in lower case. Only as a route of two known
    # codes, so ordinary three-letter words ("the", "and") are not airports.
    for a, b in _ROUTE_CODES.findall(text):
        if a.upper() in _AIRPORT_CODES and b.upper() in _AIRPORT_CODES:
            return True
    lowered = text.lower()
    return any(re.search(r"\b" + re.escape(city) + r"\b", lowered) for city in _CITY_NAMES)


def _is_aviation(text: str, include_weak: bool = True) -> bool:
    if _match_keywords(text, _KEYWORD_MAP[DomainEnum.AVIATION]) or _mentions_airport(text):
        return True
    return include_weak and _match_keywords(text, _WEAK_AVIATION_KEYWORDS)


# Greeting keywords — these are ALLOWED through to the LLM.
_GREETING_KEYWORDS = [
    "hello", "hi", "hey", "good morning", "good afternoon",
    "good evening", "howdy", "greetings", "thanks", "thank you",
    "bye", "goodbye", "see you",
    # Questions about the assistant itself. "Who are you?" got the off-topic
    # redirect, which is the one question the assistant must always answer.
    "who are you", "what are you", "what can you do", "what can you help",
    "how can you help", "what do you do", "introduce yourself", "your name", "skymind",
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
        if _match_whole_words(text, keywords):
            # Special case: if both aviation AND off-topic keywords are
            # present, aviation wins (e.g. "I'm sad my flight got cancelled")
            if _is_aviation(text, include_weak=False):
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
    if _is_aviation(text):
        return DomainClassification(
            domain=DomainEnum.AVIATION,
            intent=IntentEnum.UNKNOWN,
            scope=ScopeEnum.IN_SCOPE,
            confidence=0.95,
            reason_code="keyword_match",
            metadata={"matched_domain": "aviation"},
        )

    # Check greetings — these are allowed through to the LLM as DomainEnum.GREETING
    # Whole words: as a prefix, "hi" also matched "his", "history" and "hiking".
    if _match_whole_words(text, _GREETING_KEYWORDS):
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


