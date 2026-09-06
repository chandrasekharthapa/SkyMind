"""Automated Tests — End-to-End Live Flight Search Data Realism & Multi-Segment Fidelity."""

import pytest
from backend.services.flight_normalizer import FlightNormalizer, NormalizedFlight, NormalizedItinerary, NormalizedSegment


def test_multi_segment_connecting_flight_fidelity():
    """Verify that multi-segment connecting flights (e.g. DEL -> DXB -> LHR) preserve all legs and stops."""
    raw_connecting_flight = {
        "price": 45000.0,
        "currency": "INR",
        "primary_airline": "EK",
        "primary_airline_name": "Emirates",
        "legs": [
            {
                "airline_code": "EK",
                "airline": "Emirates",
                "flight_number": "511",
                "departure_airport": "DEL",
                "arrival_airport": "DXB",
                "departure_time": "2026-08-15T11:00:00",
                "arrival_time": "2026-08-15T13:15:00",
                "duration": 225
            },
            {
                "airline_code": "EK",
                "airline": "Emirates",
                "flight_number": "001",
                "departure_airport": "DXB",
                "arrival_airport": "LHR",
                "departure_time": "2026-08-15T16:00:00",
                "arrival_time": "2026-08-15T20:10:00",
                "duration": 430
            }
        ]
    }

    norm = FlightNormalizer.normalize_mcp_flight(
        flight=raw_connecting_flight,
        origin_iata="DEL",
        destination_iata="LHR",
        departure_date="2026-08-15"
    )

    assert norm is not None
    assert norm.primary_airline == "EK"
    assert len(norm.itineraries[0].segments) == 2, "Connecting flight must preserve both segments!"
    
    seg1 = norm.itineraries[0].segments[0]
    seg2 = norm.itineraries[0].segments[1]
    
    assert seg1.origin == "DEL" and seg1.destination == "DXB"
    assert seg2.origin == "DXB" and seg2.destination == "LHR"
    assert norm.itineraries[0].duration == "PT10H55M"


def test_deduplication_preserves_distinct_flights():
    """Verify deduplicate_flights never merges distinct flights sharing airline or price."""
    f1 = NormalizedFlight(
        id="6E-101-5000",
        primary_airline="6E",
        primary_airline_name="IndiGo",
        flight_number="6E101",
        price=5000.0,
        itineraries=[NormalizedItinerary(duration="PT2H", segments=[
            NormalizedSegment(origin="DEL", destination="BOM", departure_time="2026-08-15T06:00:00", arrival_time="2026-08-15T08:00:00", flight_number="6E101")
        ])]
    )

    f2 = NormalizedFlight(
        id="6E-202-5000",
        primary_airline="6E",
        primary_airline_name="IndiGo",
        flight_number="6E202",
        price=5000.0,
        itineraries=[NormalizedItinerary(duration="PT2H", segments=[
            NormalizedSegment(origin="DEL", destination="BOM", departure_time="2026-08-15T18:00:00", arrival_time="2026-08-15T20:00:00", flight_number="6E202")
        ])]
    )

    deduped = FlightNormalizer.deduplicate_flights([f1, f2])
    assert len(deduped) == 2, "Distinct flights with different departure times or flight numbers must NOT be merged!"
