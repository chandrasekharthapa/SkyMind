import pytest
import os
import sys
from pathlib import Path

# Add backend to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from backend.services.flight_normalizer import FlightNormalizer, NormalizedFlight, NormalizedSegment, NormalizedItinerary
from backend.services.flight_formatter import FlightSearchFormatter, RecommendationFormatter
from backend.services.recommendation_engine import RecommendationEngine

def test_duration_formatter():
    """Verify ISO 8601 duration parser formats correctly."""
    assert FlightSearchFormatter.format_duration("PT2H15M") == "2h 15m"
    assert FlightSearchFormatter.format_duration("PT135M") == "2h 15m"
    assert FlightSearchFormatter.format_duration("PT45M") == "45m"
    assert FlightSearchFormatter.format_duration("PT3H") == "3h"
    assert FlightSearchFormatter.format_duration("") == "N/A"

def test_currency_formatter():
    """Verify INR and USD formatting conventions, and that absence is not INR.

    The `currency` parameter defaulted to `"INR"` until AUDIT-FIXES.md §48, so a
    fare whose denomination nobody knew took the rupee branch and a $58 quote
    rendered `₹58`. A bare number is the honest render: it states the fare without
    claiming a unit that was never measured.
    """
    assert FlightSearchFormatter.format_currency(9330, "INR") == "₹9,330"
    assert FlightSearchFormatter.format_currency(82.5, "USD") == "$82.50"
    assert FlightSearchFormatter.format_currency(100.0, "EUR") == "100.00 EUR"
    assert FlightSearchFormatter.format_currency(58.0, None) == "58.00"
    assert FlightSearchFormatter.format_currency(58.0) == "58.00"
    # Specifically not the string "None" appended by the fallback branch.
    assert "None" not in FlightSearchFormatter.format_currency(58.0, None)

def test_flight_deduplication():
    """Verify deduplicator removes duplicate flights and keeps the cheapest option."""
    # Create segment
    s1 = NormalizedSegment(
        flight_number="6E100",
        departure_time="2026-07-26T12:00:00",
        arrival_time="2026-07-26T14:15:00",
        airline_code="6E",
        airline_name="IndiGo",
        origin="DEL",
        destination="BOM",
        duration="PT2H15M"
    )
    itinerary = NormalizedItinerary(duration="PT2H15M", segments=[s1])
    
    f1 = NormalizedFlight(
        id="6E-100-9330",
        primary_airline="6E",
        primary_airline_name="IndiGo",
        seats_available=30,
        flight_number="6E100",
        itineraries=[itinerary],
        price=9330.0,
        currency="INR"
    )
    f2 = NormalizedFlight(
        id="6E-100-9900",
        primary_airline="6E",
        primary_airline_name="IndiGo",
        seats_available=20,
        flight_number="6E100",
        itineraries=[itinerary],
        price=9900.0,
        currency="INR"
    )
    
    deduped = RecommendationEngine.deduplicate_flights([f1, f2])
    assert len(deduped) == 1
    assert deduped[0].price == 9330.0

def test_sorting_flights():
    """Verify flights are sorted by price, duration, stops, and departure time."""
    s1 = NormalizedSegment(
        flight_number="6E100",
        departure_time="2026-07-26T12:00:00",
        arrival_time="2026-07-26T14:15:00",
        airline_code="6E",
        airline_name="IndiGo",
        origin="DEL",
        destination="BOM",
        duration="PT2H"
    )
    s2 = NormalizedSegment(
        flight_number="AI101",
        departure_time="2026-07-26T08:00:00",
        arrival_time="2026-07-26T11:00:00",
        airline_code="AI",
        airline_name="Air India",
        origin="DEL",
        destination="BOM",
        duration="PT3H"
    )
    
    f1 = NormalizedFlight(
        id="6E-100-9330",
        primary_airline="6E",
        primary_airline_name="IndiGo",
        seats_available=30,
        flight_number="6E100",
        itineraries=[NormalizedItinerary(duration="PT2H", segments=[s1])],
        price=9330.0,
        currency="INR"
    )
    f2 = NormalizedFlight(
        id="AI-101-8500",
        primary_airline="AI",
        primary_airline_name="Air India",
        seats_available=20,
        flight_number="AI101",
        itineraries=[NormalizedItinerary(duration="PT3H", segments=[s2])],
        price=8500.0,
        currency="INR"
    )
    
    sorted_price = RecommendationEngine.sort_flights([f1, f2], "price")
    assert sorted_price[0].price == 8500.0
    
    sorted_dur = RecommendationEngine.sort_flights([f1, f2], "duration")
    assert sorted_dur[0].price == 9330.0

def test_recommendation_formatter():
    """Verify recommendation states based on ML threshold predictions."""
    r_book = RecommendationFormatter.format(12000.0, 10000.0) # predicted > base * 1.12
    assert r_book.action == "BOOK NOW"
    
    r_wait = RecommendationFormatter.format(8000.0, 10000.0) # predicted < base * 0.88
    assert r_wait.action == "WAIT"
    
    r_fair = RecommendationFormatter.format(10500.0, 10000.0) # predicted stable
    assert r_fair.action == "FAIR PRICE"
