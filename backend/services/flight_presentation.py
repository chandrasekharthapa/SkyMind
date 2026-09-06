"""Presentation Models.

Schemas optimized for LLM prompting and consumer-facing user interfaces
(Google Flights, Hopper, Kayak style).

`AirlinePresentation`, `PricePredictionPresentation` and `PriceTrendPresentation`
were removed with the four dead formatter classes in `flight_formatter.py` that
were their only producers; nothing consumed them either.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from backend.services.flight_normalizer import NormalizedFlight

class AirportPresentation(BaseModel):
    iata: str
    city: str
    name: str
    country: str

class RecommendationPresentation(BaseModel):
    action: str  # e.g., "BOOK NOW", "WAIT", "FAIR PRICE"
    reasoning: str
    trend: str  # e.g., "INCREASING", "DECREASING", "STABLE"

class FlightSearchPresentation(BaseModel):
    cheapest: Optional[NormalizedFlight] = None
    fastest: Optional[NormalizedFlight] = None
    best_value: Optional[NormalizedFlight] = None
    recommendation: RecommendationPresentation
    flights: List[NormalizedFlight]
    airports: List[AirportPresentation] = []
    metadata: Dict[str, Any] = {}
