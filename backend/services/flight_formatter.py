"""Response Formatting Layer.

Formats canonical flight models and recommendations into human-readable text.

Four classes were removed as dead — nothing in the repository referenced
`PricePredictionFormatter`, `TrendFormatter`, `AirportFormatter` or
`AirlineFormatter`. `TrendFormatter` is worth naming: it labelled a forecast
`RISING`/`DROPPING`/`STABLE` on hardcoded ±12% thresholds and returned advice text
("We recommend booking soon to secure this price") that no model output justified.
The live trend and recommendation path is `recommendation_engine` plus
`recommendation_policy`, and it does not use fixed percentage bands.
`PricePredictionFormatter` reported `current - predicted` as `expected_savings`,
which is a difference between a fare on offer and a point prediction, not a saving
anyone would realise.
"""

import re
from typing import Dict, Any, List, Optional
from backend.services.flight_normalizer import NormalizedFlight, NormalizedSegment
from backend.services.flight_presentation import RecommendationPresentation

class FlightSearchFormatter:
    @staticmethod
    def format_duration(iso_duration: str) -> str:
        """Convert ISO 8601 duration string (e.g. PT2H15M, PT135M) into human readable text (2h 15m)."""
        if not iso_duration:
            return "N/A"
        
        # Match H and M
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso_duration)
        if match:
            h_str = match.group(1)
            m_str = match.group(2)
            
            hours = int(h_str) if h_str else 0
            minutes = int(m_str) if m_str else 0
            
            # If no hours but minutes >= 60, convert
            if hours == 0 and minutes >= 60:
                hours = minutes // 60
                minutes = minutes % 60
                
            parts = []
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0:
                parts.append(f"{minutes}m")
                
            return " ".join(parts) if parts else "0m"
            
        return iso_duration

    @staticmethod
    def format_currency(price: float, currency: Optional[str] = None) -> str:
        """Format a fare in the currency it was quoted in, or in none at all.

        The default was `"INR"` until AUDIT-FIXES.md §48. Combined with
        `NormalizedFlight.currency`'s own `"INR"` default and the two
        `.get("currency", "INR")` call sites in `flight_normalizer`, it meant an
        unstated denomination took the first branch below and a $58 fare was
        rendered `₹58` — a plausible cheap fare rather than a visibly wrong number.
        That is the reason the 156 dollar rows recorded on 2026-07-19 sat in the UI
        unnoticed.

        With no currency, the number is shown bare. A bare number is honest about
        what is known: the fare, not its unit. Falling through to the last line
        instead would render the string "None" next to the price.
        """
        if currency is None:
            return f"{price:,.2f}"
        if currency == "INR":
            return f"₹{int(price):,}"
        elif currency == "USD":
            return f"${price:,.2f}"
        return f"{price:,.2f} {currency}"

    @staticmethod
    def to_presentation(flight: NormalizedFlight) -> Dict[str, Any]:
        """Convert a normalized flight into a UI presentation dictionary."""
        itinerary = flight.itineraries[0] if flight.itineraries else None
        duration = FlightSearchFormatter.format_duration(itinerary.duration) if itinerary else "N/A"
        segments_data = []
        
        if itinerary:
            for s in itinerary.segments:
                segments_data.append({
                    "flight_number": s.flight_number,
                    "departure_time": s.departure_time,
                    "arrival_time": s.arrival_time,
                    "carrier_code": s.airline_code,
                    "carrier_name": s.airline_name,
                    "origin_code": s.origin,
                    "destination_code": s.destination,
                    "duration": FlightSearchFormatter.format_duration(s.duration),
                    "cabin": s.cabin,
                    "stops": s.stops
                })
        
        # Pull ML metadata
        meta = getattr(flight, "metadata", {}) or {}
        if meta is None:
            meta = {}
        
        # Render itineraries in old model structure
        mapped_itineraries = []
        if itinerary:
            mapped_segments = []
            for s in itinerary.segments:
                mapped_segments.append({
                    "flight_number": s.flight_number,
                    "departure_time": s.departure_time,
                    "arrival_time": s.arrival_time,
                    "carrier_code": s.airline_code,
                    "origin_code": s.origin,
                    "destination_code": s.destination,
                })
            mapped_itineraries.append({
                "duration": itinerary.duration,
                "segments": mapped_segments
            })

        return {
            "id": flight.id,
            "primary_airline": flight.primary_airline,
            "primary_airline_name": flight.primary_airline_name,
            "seats_available": flight.seats_available,
            "flight_number": flight.flight_number,
            "itineraries": mapped_itineraries,
            "price": {
                "total": flight.price,
                "currency": flight.currency
            },
            # Formatted displays
            "price_formatted": FlightSearchFormatter.format_currency(flight.price, flight.currency),
            "duration_formatted": duration,
            # ML values
            #
            # These carried defaults until now: `ai_price` fell back to
            # `flight.price`, and trend/decision/advice to "STABLE"/"FAIR"/"Price
            # is stable." That undid the honesty fix one layer up. The enrichment
            # step deliberately *removes* `ai_price` and writes an "UNKNOWN"
            # vocabulary when the model declines or is untrained; this function put
            # the listed fare back under the name of a prediction and re-asserted a
            # verdict on it. A default here is a claim, because nothing downstream
            # can tell it apart from a number the model produced — and the one it
            # chose, the fare itself, is the number that makes any comparison
            # against the fare come out neutral.
            #
            # `meta` is empty exactly when a flight reaches presentation without
            # passing through `_enrich_with_ml`, which is the case the defaults were
            # papering over. `ml_available` is written on all three enrichment
            # branches, so its absence means enrichment never ran; the rest of the
            # vocabulary below is the same one enrichment uses for "no forecast", so
            # a consumer has one contract to read rather than two.
            "ml_available": bool(meta.get("ml_available", False)),
            "ai_price": meta.get("ai_price"),
            "recommendation": meta.get("recommendation", "MONITOR"),
            "trend": meta.get("trend", "UNKNOWN"),
            "decision": meta.get("decision", "UNKNOWN"),
            "advice": meta.get(
                "advice", "No price forecast available for this flight."
            ),
        }

class RecommendationFormatter:
    @staticmethod
    def unavailable(reason: str) -> RecommendationPresentation:
        """A recommendation for when there is nothing to base one on.

        Callers used to synthesise this case as `format(1.0, 1.0)`, two placeholder
        numbers that fall through to the neutral branch below and produce
        "FAIR PRICE" / "Current price is within normal limits." / "STABLE" — a
        definite verdict on a fare, issued when no fare and no prediction existed.
        Say so instead.
        """
        return RecommendationPresentation(
            action="NO RECOMMENDATION",
            reasoning=reason,
            trend="UNKNOWN"
        )

    @staticmethod
    def format(predicted_price: float, base_price: float) -> RecommendationPresentation:
        if predicted_price > base_price * 1.12:
            return RecommendationPresentation(
                action="BOOK NOW",
                reasoning="Fares are expected to rise. Lock in the price today.",
                trend="INCREASING"
            )
        elif predicted_price < base_price * 0.88:
            return RecommendationPresentation(
                action="WAIT",
                reasoning="Expected price drops ahead. Monitor the route.",
                trend="DECREASING"
            )
        return RecommendationPresentation(
            action="FAIR PRICE",
            reasoning="Current price is within normal limits.",
            trend="STABLE"
        )
