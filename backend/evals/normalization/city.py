"""City Name Normalizer for SkyMind Evaluation Platform."""

import re
from typing import Optional

CITY_ALIASES = {
    "DELHI": "Delhi", "NEW DELHI": "Delhi", "DEL": "Delhi",
    "MUMBAI": "Mumbai", "BOMBAY": "Mumbai", "BOM": "Mumbai",
    "BANGALORE": "Bengaluru", "BENGALURU": "Bengaluru", "BLR": "Bengaluru",
    "CHENNAI": "Chennai", "MADRAS": "Chennai", "MAA": "Chennai",
    "KOLKATA": "Kolkata", "CALCUTTA": "Kolkata", "CCU": "Kolkata",
    "HYDERABAD": "Hyderabad", "HYD": "Hyderabad",
    "GOA": "Goa", "GOI": "Goa",
    "COCHIN": "Kochi", "KOCHI": "Kochi", "COK": "Kochi",
    "BHUBANESWAR": "Bhubaneswar", "BBI": "Bhubaneswar",
    "AHMEDABAD": "Ahmedabad", "AMD": "Ahmedabad",
    "PUNE": "Pune", "PNQ": "Pune",
    "NEW YORK": "New York City", "NYC": "New York City", "JFK": "New York City",
    "LONDON": "London", "LHR": "London"
}


def normalize_city(city_text: Optional[str]) -> Optional[str]:
    """Resolves city alias or code to standardized title-case city name."""
    if not city_text:
        return None
    cleaned = re.sub(r"[^\w\s]", "", str(city_text)).strip().upper()
    return CITY_ALIASES.get(cleaned, cleaned.title() if cleaned else None)
