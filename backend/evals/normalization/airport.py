"""Airport Code and Alias Normalizer for SkyMind Evaluation Platform."""

import re
from typing import Optional

CITY_OR_ALIAS_TO_IATA = {
    "DELHI": "DEL", "NEW DELHI": "DEL", "DEL": "DEL", "INDIRA GANDHI": "DEL",
    "MUMBAI": "BOM", "BOMBAY": "BOM", "BOM": "BOM", "CHHATRAPATI SHIVAJI": "BOM",
    "BANGALORE": "BLR", "BENGALURU": "BLR", "BLR": "BLR", "KEMPEGOWDA": "BLR",
    "CHENNAI": "MAA", "MADRAS": "MAA", "MAA": "MAA",
    "KOLKATA": "CCU", "CALCUTTA": "CCU", "CCU": "CCU", "NETAJI SUBHASH": "CCU",
    "HYDERABAD": "HYD", "HYD": "HYD", "RAJIV GANDHI": "HYD",
    "GOA": "GOI", "GOI": "GOI", "MOPA": "GOX", "GOX": "GOX",
    "COCHIN": "COK", "KOCHI": "COK", "COK": "COK",
    "BHUBANESWAR": "BBI", "BBI": "BBI",
    "AHMEDABAD": "AMD", "AMD": "AMD",
    "PUNE": "PNQ", "PNQ": "PNQ",
    "NEW YORK": "JFK", "NYC": "JFK", "JFK": "JFK", "EWR": "EWR", "LGA": "LGA",
    "LONDON": "LHR", "HEATHROW": "LHR", "LHR": "LHR", "LGW": "LGW",
    "DUBAI": "DXB", "DXB": "DXB"
}


def normalize_airport(input_text: Optional[str]) -> Optional[str]:
    """Resolves city name, airport name, or code into canonical 3-letter IATA code."""
    if not input_text:
        return None
    cleaned = re.sub(r"[^\w\s]", "", str(input_text)).strip().upper()
    if len(cleaned) == 3 and cleaned.isalpha():
        return CITY_OR_ALIAS_TO_IATA.get(cleaned, cleaned)
    return CITY_OR_ALIAS_TO_IATA.get(cleaned)
