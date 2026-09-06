"""Automated Production Integrity Regression Tests — Zero Synthetic Flight Data."""

import pytest
from backend.services.flight_normalizer import FlightNormalizer


def test_db_flight_normalization_zero_synthetic_data():
    """Verify that cached price history records never fabricate fake schedule details."""
    db_record = {
        "origin_code": "DEL",
        "destination_code": "BOM",
        "price": 5499.0,
        "recorded_at": "2026-07-20T10:00:00Z"
    }

    norm = FlightNormalizer.normalize_db_flight(
        db_flight=db_record,
        origin_iata="DEL",
        destination_iata="BOM",
        departure_date="2026-08-15"
    )

    assert norm is not None
    assert norm.provenance == "HISTORICAL_OBSERVATION"
    assert norm.flight_number is None, "Must NEVER fabricate dummy flight numbers like 6E1000"
    
    seg = norm.itineraries[0].segments[0]
    assert seg.departure_time is None, "Must NEVER fabricate fake 12:00 PM departure times"
    assert seg.arrival_time is None, "Must NEVER fabricate fake 14:15 PM arrival times"
    assert seg.duration is None, "Must NEVER fabricate fake PT2H15M durations"
    assert seg.airline_code == "UNKNOWN"
    assert seg.airline_name == "Unknown Carrier"


def test_mcp_flight_normalization_preserves_nulls():
    """Verify raw provider normalization preserves nulls when schedule attributes are missing."""
    raw_mcp_flight = {
        "price": 4200.0,
        "currency": "INR"
    }

    norm = FlightNormalizer.normalize_mcp_flight(
        flight=raw_mcp_flight,
        origin_iata="DEL",
        destination_iata="BOM",
        departure_date="2026-08-15"
    )

    assert norm is not None
    assert norm.provenance == "REAL_PROVIDER"
    assert norm.flight_number is None
    seg = norm.itineraries[0].segments[0]
    assert seg.departure_time is None
    assert seg.arrival_time is None
    assert seg.duration is None
