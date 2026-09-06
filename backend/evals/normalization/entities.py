"""Entity Field Normalizer for SkyMind Evaluation Platform."""

from typing import Dict, Any
from backend.evals.normalization.airport import normalize_airport
from backend.evals.normalization.city import normalize_city
from backend.evals.normalization.dates import normalize_date


def normalize_entities(entities: Dict[str, Any]) -> Dict[str, Any]:
    """Standardizes entity dictionary fields (origin, destination, date, cabin_class)."""
    if not isinstance(entities, dict):
        return {}

    normalized = {}
    for key, val in entities.items():
        if not val:
            continue
        k_lower = key.lower()

        if k_lower in ("origin", "origin_iata", "from"):
            normalized["origin_iata"] = normalize_airport(val)
            normalized["origin_city"] = normalize_city(val)
        elif k_lower in ("destination", "destination_iata", "to"):
            normalized["destination_iata"] = normalize_airport(val)
            normalized["destination_city"] = normalize_city(val)
        elif k_lower in ("departure_date", "departure_date_iso", "date"):
            normalized["departure_date"] = normalize_date(val)
        elif k_lower in ("cabin", "cabin_class"):
            normalized["cabin_class"] = str(val).upper()
        else:
            normalized[key] = val

    return normalized
