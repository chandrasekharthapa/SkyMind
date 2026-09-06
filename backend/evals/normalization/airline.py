"""Airline Name and Code Normalizer for SkyMind Evaluation Platform.

Mirrors `airport.py` for carriers. Two differences from the airport table matter:

  * Airline IATA codes are two characters and may contain a digit (`6E`, `G8`,
    `I5`), so the "looks like a code" shortcut cannot test `isalpha()`.
  * The alias set is genuinely ambiguous by prefix: `AIR INDIA` (AI) is a prefix
    of `AIR INDIA EXPRESS` (IX). Asking "does any alias for IX appear in this
    text" is therefore not enough — the query "Air India Express to Kochi"
    contains an alias for AI as well. `airline_codes_mentioned` resolves this by
    keeping only *maximal* matches: an alias is credited only when no longer
    alias also appears in the text and subsumes it.

Codes and names are the ones the ingestion layer already recognises
(`MarketDataController.AIRLINE_NAMES` in `backend/services/ingestion_controller.py`);
this module is a separate copy on purpose, so that an evaluator does not have to
import the ingestion stack and its Supabase dependencies to normalize a string.
"""

import re
from typing import Dict, List, Optional, Set

# Canonical code -> display name, matching the ingestion layer's table.
IATA_TO_AIRLINE_NAME: Dict[str, str] = {
    "6E": "IndiGo",
    "AI": "Air India",
    "IX": "Air India Express",
    "QP": "Akasa Air",
    "UK": "Vistara",
    "SG": "SpiceJet",
    "G8": "Go First",
    "S5": "Star Air",
    "2T": "TruJet",
    "I5": "AirAsia India",
    "9I": "Alliance Air",
}

# Every spelling a query might use, upper-cased, punctuation stripped.
AIRLINE_ALIAS_TO_IATA: Dict[str, str] = {
    "6E": "6E", "INDIGO": "6E", "INDI GO": "6E",
    "AI": "AI", "AIR INDIA": "AI", "AIRINDIA": "AI",
    "IX": "IX", "AIR INDIA EXPRESS": "IX", "AI EXPRESS": "IX", "AIRINDIA EXPRESS": "IX",
    "QP": "QP", "AKASA": "QP", "AKASA AIR": "QP", "AKASAAIR": "QP",
    "UK": "UK", "VISTARA": "UK", "TATA SIA": "UK",
    "SG": "SG", "SPICEJET": "SG", "SPICE JET": "SG",
    "G8": "G8", "GO FIRST": "G8", "GOFIRST": "G8", "GOAIR": "G8", "GO AIR": "G8",
    "S5": "S5", "STAR AIR": "S5", "STARAIR": "S5",
    "2T": "2T", "TRUJET": "2T", "TRU JET": "2T",
    "I5": "I5", "AIRASIA": "I5", "AIR ASIA": "I5",
    "AIRASIA INDIA": "I5", "AIR ASIA INDIA": "I5",
    "9I": "9I", "ALLIANCE AIR": "9I", "ALLIANCEAIR": "9I",
}

# Reverse index: code -> every alias that resolves to it.
IATA_TO_ALIASES: Dict[str, List[str]] = {}
for _alias, _code in AIRLINE_ALIAS_TO_IATA.items():
    IATA_TO_ALIASES.setdefault(_code, []).append(_alias)

_CODE_RE = re.compile(r"^[0-9A-Z]{2}$")


def _clean(text: str) -> str:
    """Upper-case, drop punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(text))).strip().upper()


def normalize_airline(input_text: Optional[str]) -> Optional[str]:
    """Resolves an airline name or code into its canonical 2-character IATA code.

    Returns the cleaned input unchanged when it already looks like a code this
    table does not carry, and `None` when the input is neither a known alias nor
    code-shaped — the same contract `normalize_airport` follows.
    """
    if not input_text:
        return None
    cleaned = _clean(input_text)
    if not cleaned:
        return None
    hit = AIRLINE_ALIAS_TO_IATA.get(cleaned)
    if hit:
        return hit
    if _CODE_RE.match(cleaned):
        return cleaned
    return None


def _appears(haystack: str, needle: str) -> bool:
    """Whole-word/phrase containment, so `AI` does not match `AIRPORT`."""
    if not needle:
        return False
    return re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack) is not None


def airline_codes_mentioned(text: Optional[str]) -> Set[str]:
    """Every airline this text names, by canonical code.

    Only *maximal* aliases count. `AIR INDIA` appears inside `AIR INDIA EXPRESS`,
    so crediting both would report a mention of AI in a sentence that names only
    IX. An alias is dropped when a longer alias that also appears in the text
    contains it.
    """
    if not text:
        return set()
    cleaned = _clean(text)
    if not cleaned:
        return set()

    present = [alias for alias in AIRLINE_ALIAS_TO_IATA if _appears(cleaned, alias)]
    maximal = [
        alias for alias in present
        if not any(other != alias and alias in other for other in present)
    ]
    return {AIRLINE_ALIAS_TO_IATA[alias] for alias in maximal}
