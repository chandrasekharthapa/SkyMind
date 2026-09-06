"""SkyMind Domain Models — Market Snapshot.

Canonical shared representation of the live flight market context.
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

class MarketSnapshot(BaseModel):
    """Canonical representation of the current live flight market status."""
    lowest_fare: float = Field(..., description="Lowest flight fare observed in the market.")
    highest_fare: float = Field(..., description="Highest flight fare observed in the market.")
    average_fare: float = Field(..., description="Mean of all observed flight fares.")
    median_fare: float = Field(..., description="Median of all observed flight fares.")
    fare_spread: float = Field(..., description="Difference between highest and lowest fares.")
    price_std_dev: float = Field(..., description="Standard deviation of observed flight fares.")
    
    total_live_flights: int = Field(..., description="Total count of active flights found.")
    direct_flight_count: int = Field(..., description="Number of direct non-stop flights.")
    connecting_flight_count: int = Field(..., description="Number of connecting flights with one or more stops.")

    # Which flight the lowest fare belongs to.
    #
    # `lowest_fare` is the number the prediction is *about*: it is what the caller
    # is quoted and what the model is given as the current price. Every other field
    # here is an aggregate, so until these two were added the snapshot could say
    # what the cheapest fare was and not whose it was — and two consumers filled
    # the gap by guessing. `prediction_service` took its airline from
    # `list(airline_distribution.keys())[0]`, an arbitrary carrier from a dict built
    # in provider order, so the airline features described one flight while the
    # price described another; and it named no flight at all, which left every
    # booking-curve, volatility and trend feature computed over a window one
    # observation long. Null when the provider gave no fare, or gave the cheapest
    # one without an airline or a number.
    cheapest_airline: Optional[str] = Field(None, description="Airline operating the flight whose fare is `lowest_fare`.")
    cheapest_flight_number: Optional[str] = Field(None, description="Flight number of the flight whose fare is `lowest_fare`.")

    # Two more properties of that same flight, for the same reason.
    #
    # `seats_available` and `departure_time` are per-flight columns in
    # `price_history`, so the model was trained on one flight's seat count and one
    # flight's departure hour. The snapshot carried only aggregates of them — a
    # mean seat count over every flight on the route, and a three-bucket
    # morning/afternoon/evening histogram — and `prediction_service` reconstructed
    # per-flight values from those aggregates: seats became the market mean, and the
    # departure time became `T08`, `T14` or `T20` depending on which bucket was
    # non-empty. Both were then fed to the model under the names of the per-flight
    # features it had been fitted on. Carrying the real values means the serving
    # path can pass what it observed, or nothing.
    #
    # Null whenever the provider did not report them, and the consumer then sends
    # NaN. A missing seat count is not fifteen seats, and a flight whose departure
    # time nobody reported does not leave at eight in the morning.
    cheapest_seats_available: Optional[int] = Field(None, description="Seats reported for the flight whose fare is `lowest_fare`.")
    cheapest_departure_time: Optional[str] = Field(None, description="Departure time reported for the flight whose fare is `lowest_fare`.")

    # The same question asked per carrier: `{airline_code: {"fare": float,
    # "flight_number": Optional[str], "seats_available": Optional[int],
    # "departure_time": Optional[str]}}` — the cheapest flight each airline is
    # offering in this snapshot, and the properties of that flight.
    #
    # Needed because `lowest_fare` is the whole market's minimum, and a caller may
    # name the airline they are asking about. `prediction_service` quoted
    # `lowest_fare` either way, so a request about AI was answered with the fare of
    # whichever carrier happened to be cheapest — the price, the airline features
    # and the recommendation all describing different flights. A carrier absent
    # from this mapping is not flying the route in this snapshot, which is a
    # different thing from flying it at an unknown price, and the caller is told
    # there is no live fare rather than given someone else's.
    #
    # Shaped as a plain dict for the same reason `seat_information` is: a small
    # statistic bundle that crosses the layer boundary unchanged.
    cheapest_by_airline: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Per-airline cheapest flight: code -> {fare, flight_number, seats_available, departure_time}.")

    airline_distribution: Dict[str, int] = Field(default_factory=dict, description="Distribution of flights per airline code.")
    departure_distribution: Dict[str, int] = Field(default_factory=dict, description="Morning, afternoon, evening flight counts. An aggregate — not a source for any one flight's departure time; see `cheapest_departure_time`.")
    seat_information: Optional[Dict[str, Any]] = Field(None, description="Route-wide seat availability stats (min, max, average) if available. An aggregate — not a source for any one flight's seat count; see `cheapest_seats_available`.")
    
    retrieval_timestamp: str = Field(..., description="ISO 8601 timestamp representing when snapshot was fetched.")
    provider: str = Field(..., description="Authoritative provider of the raw flights search (e.g. MCP Google Flights).")
    search_duration: float = Field(0.0, description="Time taken in seconds to run the live search query.")
    search_success: bool = Field(True, description="Indicates whether the search completed successfully.")

    # Upstream data quality metrics
    snapshot_quality: float = Field(1.0, description="Quality score (0.0 to 1.0) of this market snapshot.")
    snapshot_completeness: float = Field(1.0, description="Percentage of flights containing valid fares and durations.")
    missing_fields: List[str] = Field(default_factory=list, description="List of attributes containing missing or null data.")
    provider_status: str = Field("ONLINE", description="Status of the upstream API provider (ONLINE, DEGRADED, OFFLINE).")

    # Cache metadata
    snapshot_age: float = Field(0.0, description="Age in seconds of the retrieved snapshot.")
    cache_hit: bool = Field(False, description="Whether snapshot was served from cache.")
    cache_miss: bool = Field(False, description="Whether snapshot was freshly queried.")
    refresh_reason: str = Field("TTL_EXPIRED", description="Reason for cache refresh.")
