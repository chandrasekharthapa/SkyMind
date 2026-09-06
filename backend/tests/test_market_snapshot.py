import pytest
import sys
import os
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.domain.market_snapshot import MarketSnapshot
from backend.services.market_snapshot_provider import market_snapshot_provider

def test_market_snapshot_aggregates():
    """Verify statistics aggregates calculation in market snapshot."""
    flights = [
        {"flight_number": "6E101", "price": {"total": 5000.0, "currency": "INR"}, "primary_airline": "6E", "itineraries": [{"segments": [{"departure_time": "2026-07-26T08:00:00"}]}], "seats_available": 10},
        {"flight_number": "AI202", "price": {"total": 9000.0, "currency": "INR"}, "primary_airline": "AI", "itineraries": [{"segments": [{"departure_time": "2026-07-26T14:00:00"}]}], "seats_available": 20},
        {"flight_number": "UK303", "price": {"total": 7000.0, "currency": "INR"}, "primary_airline": "UK", "itineraries": [{"segments": [{"departure_time": "2026-07-26T19:00:00"}]}], "seats_available": 15}
    ]
    
    snapshot = market_snapshot_provider._build_snapshot(flights, "Test Provider", 0.5, True)
    
    assert snapshot.lowest_fare == 5000.0
    assert snapshot.highest_fare == 9000.0
    assert snapshot.average_fare == 7000.0
    assert snapshot.median_fare == 7000.0
    assert snapshot.fare_spread == 4000.0
    assert snapshot.total_live_flights == 3
    assert snapshot.direct_flight_count == 3
    assert snapshot.connecting_flight_count == 0
    assert snapshot.airline_distribution == {"6E": 1, "AI": 1, "UK": 1}
    assert snapshot.departure_distribution == {"morning": 1, "afternoon": 1, "evening": 1}
    assert snapshot.seat_information["min"] == 10
    assert snapshot.seat_information["max"] == 20
    assert snapshot.seat_information["average"] == 15.0
    assert snapshot.snapshot_quality == 1.0
    assert snapshot.snapshot_completeness == 1.0
    # Whose fare `lowest_fare` is. Every other field above is an aggregate, and
    # until these existed the snapshot could say what the cheapest fare was and
    # not which flight it belonged to, so `prediction_service` took its airline
    # from the first key of `airline_distribution` — "6E" here only by insertion
    # order — and named no flight at all.
    assert snapshot.cheapest_airline == "6E"
    assert snapshot.cheapest_flight_number == "6E101"
    assert snapshot.cheapest_seats_available == 10
    assert snapshot.cheapest_departure_time == "2026-07-26T08:00:00"
    assert snapshot.cheapest_by_airline == {
        "6E": {"fare": 5000.0, "flight_number": "6E101",
               "seats_available": 10, "departure_time": "2026-07-26T08:00:00"},
        "AI": {"fare": 9000.0, "flight_number": "AI202",
               "seats_available": 20, "departure_time": "2026-07-26T14:00:00"},
        "UK": {"fare": 7000.0, "flight_number": "UK303",
               "seats_available": 15, "departure_time": "2026-07-26T19:00:00"},
    }
    assert "cheapest_flight_number" not in snapshot.missing_fields


def test_the_cheapest_flight_is_not_the_first_one_listed():
    """The identity has to be the minimum's, not the response's first entry.

    `airline_distribution` is built in provider order, so reading the airline out
    of its first key returned "AI" for a market whose cheapest fare is 6E's. This
    fixture puts the cheapest flight last, where every order-dependent shortcut
    gets it wrong.
    """
    flights = [
        {"flight_number": "AI202", "price": {"total": 9000.0}, "primary_airline": "AI"},
        {"flight_number": "UK303", "price": {"total": 7000.0}, "primary_airline": "UK"},
        {"flight_number": "6E101", "price": {"total": 5000.0}, "primary_airline": "6E"},
    ]

    snapshot = market_snapshot_provider._build_snapshot(flights, "Test Provider", 0.5, True)

    assert list(snapshot.airline_distribution)[0] == "AI"
    assert snapshot.lowest_fare == 5000.0
    assert snapshot.cheapest_airline == "6E"
    assert snapshot.cheapest_flight_number == "6E101"
    # A carrier the caller names is quoted its own cheapest flight, not the
    # market's: asking about AI here is a 9000.0 question.
    assert snapshot.cheapest_by_airline["AI"] == {
        "fare": 9000.0, "flight_number": "AI202",
        "seats_available": None, "departure_time": None,
    }


def test_the_cheapest_flights_seats_and_departure_time_are_its_own():
    """Per-flight values, not the route's aggregates.

    `prediction_service` used to send the model `seat_information["average"]`
    under the per-flight name `seats_available`, and a departure time
    reconstructed from `departure_distribution` — `T08:00:00` whenever any flight
    on the route left in the morning, chosen by an `if/elif` chain that stopped at
    the first non-empty bucket.

    This fixture separates the two readings. The cheapest flight leaves at 21:40
    with 4 seats, while the route's mean seat count is 38 and its first non-empty
    bucket is morning, so the old derivation would have produced 38 seats and an
    08:00 departure for a flight that has neither.
    """
    flights = [
        {"flight_number": "AI202", "price": {"total": 9000.0}, "primary_airline": "AI",
         "itineraries": [{"segments": [{"departure_time": "2026-07-26T07:05:00"}]}],
         "seats_available": 72},
        {"flight_number": "6E101", "price": {"total": 5000.0}, "primary_airline": "6E",
         "itineraries": [{"segments": [{"departure_time": "2026-07-26T21:40:00"}]}],
         "seats_available": 4},
    ]

    snapshot = market_snapshot_provider._build_snapshot(flights, "Test Provider", 0.5, True)

    assert snapshot.cheapest_flight_number == "6E101"
    assert snapshot.cheapest_seats_available == 4
    assert snapshot.cheapest_departure_time == "2026-07-26T21:40:00"
    # What the aggregates say, so the three assertions above cannot be satisfied
    # by reading them instead.
    assert snapshot.seat_information["average"] == 38.0
    assert snapshot.departure_distribution == {"morning": 1, "afternoon": 0, "evening": 1}
    assert snapshot.cheapest_by_airline["AI"] == {
        "fare": 9000.0, "flight_number": "AI202",
        "seats_available": 72, "departure_time": "2026-07-26T07:05:00",
    }


def test_a_cheapest_flight_with_no_seats_or_departure_time_reports_neither():
    """Absent per-flight values stay absent even when the route has them.

    This is the fixture the two substitutions were built for: the route reports 30
    seats and a morning departure, and the flight being quoted reports neither. It
    has no seat count and no departure time, not thirty seats and an 08:00
    departure.
    """
    flights = [
        {"flight_number": "AI202", "price": {"total": 9000.0}, "primary_airline": "AI",
         "itineraries": [{"segments": [{"departure_time": "2026-07-26T09:15:00"}]}],
         "seats_available": 30},
        {"flight_number": "6E101", "price": {"total": 5000.0}, "primary_airline": "6E"},
    ]

    snapshot = market_snapshot_provider._build_snapshot(flights, "Test Provider", 0.5, True)

    assert snapshot.cheapest_flight_number == "6E101"
    assert snapshot.cheapest_seats_available is None
    assert snapshot.cheapest_departure_time is None
    assert snapshot.seat_information["average"] == 30.0
    assert snapshot.departure_distribution["morning"] == 1


def test_a_carriers_cheapest_flight_is_that_carriers_minimum():
    """Two flights per airline, and the cheaper one wins within each."""
    flights = [
        {"flight_number": "6E101", "price": {"total": 6000.0}, "primary_airline": "6E"},
        {"flight_number": "6E999", "price": {"total": 5200.0}, "primary_airline": "6E"},
        {"flight_number": "AI202", "price": {"total": 9000.0}, "primary_airline": "AI"},
        {"flight_number": "AI777", "price": {"total": 8100.0}, "primary_airline": "AI"},
    ]

    snapshot = market_snapshot_provider._build_snapshot(flights, "Test Provider", 0.5, True)

    assert snapshot.cheapest_by_airline == {
        "6E": {"fare": 5200.0, "flight_number": "6E999",
               "seats_available": None, "departure_time": None},
        "AI": {"fare": 8100.0, "flight_number": "AI777",
               "seats_available": None, "departure_time": None},
    }
    assert snapshot.cheapest_flight_number == "6E999"


def test_an_unpriced_flight_cannot_be_the_cheapest_one():
    """A flight the provider gave no readable fare for is not a candidate.

    It is absent from `prices` too, so counting it as the cheapest would name a
    flight whose fare is not `lowest_fare`.
    """
    flights = [
        {"flight_number": "6E101", "price": {"total": None}, "primary_airline": "6E"},
        {"flight_number": "AI202", "price": {"total": "not-a-number"}, "primary_airline": "AI"},
        {"flight_number": "UK303", "price": {"total": 0.0}, "primary_airline": "UK"},
        {"flight_number": "SG404", "price": {"total": 7000.0}, "primary_airline": "SG"},
    ]

    snapshot = market_snapshot_provider._build_snapshot(flights, "Test Provider", 0.5, True)

    assert snapshot.lowest_fare == 7000.0
    assert snapshot.cheapest_airline == "SG"
    assert snapshot.cheapest_flight_number == "SG404"
    assert set(snapshot.cheapest_by_airline) == {"SG"}


def test_a_cheapest_flight_with_no_number_is_reported_as_missing():
    """The provider priced it but did not name it, so it is on no booking curve.

    Recorded in `missing_fields` because it costs the consumer fourteen features
    and is a property of the response, not of the consumer.
    """
    flights = [
        {"price": {"total": 5000.0}, "primary_airline": "6E"},
        {"flight_number": "AI202", "price": {"total": 9000.0}, "primary_airline": "AI"},
    ]

    snapshot = market_snapshot_provider._build_snapshot(flights, "Test Provider", 0.5, True)

    assert snapshot.cheapest_airline == "6E"
    assert snapshot.cheapest_flight_number is None
    assert "cheapest_flight_number" in snapshot.missing_fields
    assert snapshot.cheapest_by_airline["6E"] == {
        "fare": 5000.0, "flight_number": None,
        "seats_available": None, "departure_time": None,
    }


def test_market_snapshot_empty():
    """Verify market snapshot builder gracefully handles empty search results."""
    snapshot = market_snapshot_provider._build_snapshot([], "Test Provider", 0.1, True)
    assert np.isnan(snapshot.lowest_fare)
    assert snapshot.total_live_flights == 0
    assert snapshot.snapshot_quality == 0.0
    # No flights, so no cheapest one — and nothing to report as missing beyond
    # the flights themselves.
    assert snapshot.cheapest_airline is None
    assert snapshot.cheapest_flight_number is None
    assert snapshot.cheapest_seats_available is None
    assert snapshot.cheapest_departure_time is None
    assert snapshot.cheapest_by_airline == {}
    assert snapshot.missing_fields == ["flights_data"]
