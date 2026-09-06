"""Flight Normalization Layer.

Converts provider-specific flight schemas into canonical, validated Pydantic
models. Two shapes arrive here: cards scraped from Google Flights and relayed by
the local MCP server (`normalize_mcp_flight`), and rows read back from the
Supabase `price_history` cache (`normalize_db_flight`).

Neither path fabricates a schedule. Every optional field is passed through as
`None` when the source did not carry it, which is why `NormalizedSegment` declares
`flight_number`, `departure_time`, `arrival_time`, `duration` and `stops` as
`Optional`. `normalize_db_flight` used to fill those with a 12:00 departure, a
14:15 arrival, `PT2H15M`, `f"{carrier}1000"` and `6E`/IndiGo, which is what made
several cached results on one route render as the same flight.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from backend.domain.provenance import decode_currency

class NormalizedSegment(BaseModel):
    flight_number: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    airline_code: Optional[str] = None
    airline_name: Optional[str] = None
    origin: str
    destination: str
    duration: Optional[str] = None  # ISO 8601 format e.g. PT2H15M
    stops: Optional[int] = None
    cabin: str = "ECONOMY"
    provenance: str = "REAL_PROVIDER"

class NormalizedItinerary(BaseModel):
    duration: Optional[str] = None
    segments: List[NormalizedSegment]

class NormalizedFlight(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    id: str
    primary_airline: str
    primary_airline_name: str
    seats_available: Optional[int] = None
    flight_number: Optional[str] = None
    itineraries: List[NormalizedItinerary]
    price: float
    # A fare without its unit is not a fare, so this is Optional and defaults to
    # absent. It read `str = "INR"` until AUDIT-FIXES.md §48, and both call sites
    # below reached it through `.get("currency", "INR")`, so a card the scraper
    # relayed with no currency became a rupee fare here and was rendered as
    # `₹{int(price):,}` by `flight_formatter.format_currency`. That is why the 156
    # dollar fares stored on 2026-07-19 were invisible in the UI: $58 displayed
    # as ₹58, an ordinary-looking cheap fare rather than a wrong number.
    currency: Optional[str] = None
    provenance: str = "REAL_PROVIDER"
    metadata: Optional[Dict[str, Any]] = None

    def __getitem__(self, item: str) -> Any:
        if item == "price":
            return {"total": self.price, "currency": self.currency}
        if hasattr(self, item):
            val = getattr(self, item)
            return val
        raise KeyError(item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item) or item == "price"

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except (KeyError, AttributeError):
            return default

class FlightNormalizer:
    @staticmethod
    def deduplicate_flights(flights: List[NormalizedFlight]) -> List[NormalizedFlight]:
        """Merge identical flights by carrier, flight_number, origin, destination, and departure_time, keeping lowest price."""
        seen = {}
        for f in flights:
            itinerary = f.itineraries[0] if (f.itineraries and len(f.itineraries) > 0) else None
            if itinerary and itinerary.segments and any(s.flight_number and s.departure_time for s in itinerary.segments):
                sig_parts = []
                for s in itinerary.segments:
                    fl_num_str = s.flight_number or "NO_NUM"
                    dep_t_str = s.departure_time or "NO_TIME"
                    sig_parts.append(f"{f.primary_airline}-{fl_num_str}-{s.origin}-{s.destination}-{dep_t_str}")
                sig = "|".join(sig_parts)
            else:
                # Include f.id or price to prevent merging distinct flights with missing schedule attributes
                sig = f"{f.primary_airline}-{f.id}-{f.price}"
            
            if sig not in seen:
                seen[sig] = f
            else:
                if f.price < seen[sig].price:
                    seen[sig] = f
                    
        return list(seen.values())

    @staticmethod
    def normalize_db_flight(db_flight: Dict[str, Any], origin_iata: str, destination_iata: str, departure_date: str) -> Optional[NormalizedFlight]:
        """Normalize Supabase price_history cached records without synthetic schedule injection."""
        price_val = db_flight.get("price")
        if price_val is None:
            return None
        try:
            price = float(price_val)
            if price <= 0.0:
                return None
        except (ValueError, TypeError):
            return None

        carrier = db_flight.get("airline_code") or "UNKNOWN"
        airline_name = db_flight.get("airline_name") or (carrier if carrier != "UNKNOWN" else "Unknown Carrier")
        flight_num = db_flight.get("flight_number")  # None if absent
        
        dep_time = db_flight.get("departure_time")  # None if absent
        arr_time = db_flight.get("arrival_time")  # None if absent
        duration_val = db_flight.get("duration")  # None if absent
        
        segment = NormalizedSegment(
            flight_number=flight_num,
            departure_time=dep_time,
            arrival_time=arr_time,
            airline_code=carrier,
            airline_name=airline_name,
            origin=origin_iata,
            destination=destination_iata,
            duration=duration_val,
            stops=db_flight.get("stops"),
            cabin=db_flight.get("cabin_class", "ECONOMY"),
            provenance="HISTORICAL_OBSERVATION"
        )
        
        itinerary = NormalizedItinerary(
            duration=duration_val,
            segments=[segment]
        )
        
        seats_val = db_flight.get("seats_available")
        seats = int(seats_val) if seats_val is not None else None
        
        flight_id_str = f"{carrier}-{flight_num or 'HIST'}-{price}"

        return NormalizedFlight(
            id=flight_id_str,
            primary_airline=carrier,
            primary_airline_name=airline_name,
            seats_available=seats,
            flight_number=flight_num,
            itineraries=[itinerary],
            price=price,
            # Decoded, not assumed. A cached row whose `currency` was never
            # measured reads back as NULL, and NULL must stay absent rather than
            # become the corpus currency on the way to the screen.
            currency=decode_currency(db_flight.get("currency")),
            provenance="HISTORICAL_OBSERVATION"
        )

    @staticmethod
    def normalize_mcp_flight(flight: Dict[str, Any], origin_iata: str, destination_iata: str, departure_date: str, cabin_class: str = "ECONOMY") -> Optional[NormalizedFlight]:
        """Normalize a raw card relayed by the MCP server, without synthetic fallbacks."""
        price_val = flight.get("price")
        if price_val is None:
            return None
        try:
            price = float(price_val)
            if price <= 0.0:
                return None
        except (ValueError, TypeError):
            return None

        seats_val = flight.get("seats") or flight.get("seats_available")
        seats = int(seats_val) if seats_val is not None else None
        primary_airline = flight.get("primary_airline") or flight.get("airline_code")
        primary_airline_name = flight.get("primary_airline_name") or flight.get("airline_name")

        if "legs" in flight and isinstance(flight["legs"], list) and flight["legs"]:
            legs = flight["legs"]
            if not primary_airline:
                primary_airline = legs[0].get("airline_code") or "UNKNOWN"
            if not primary_airline_name:
                primary_airline_name = legs[0].get("airline") or (primary_airline if primary_airline != "UNKNOWN" else "Unknown Carrier")
            
            segments = []
            total_duration = 0
            has_dur = False
            for leg in legs:
                leg_carrier = leg.get("airline_code") or primary_airline or "UNKNOWN"
                leg_airline_name = leg.get("airline") or primary_airline_name or "Unknown Carrier"
                leg_flight_num = leg.get("flight_number")  # None if absent
                if leg_flight_num and leg_carrier != "UNKNOWN" and not leg_flight_num.startswith(leg_carrier):
                    leg_flight_num = f"{leg_carrier}{leg_flight_num}"
                    
                dur = leg.get("duration")
                if isinstance(dur, (int, float)):
                    total_duration += dur
                    has_dur = True
                
                segments.append(NormalizedSegment(
                    flight_number=leg_flight_num,
                    airline_code=leg_carrier,
                    airline_name=leg_airline_name,
                    origin=leg.get("departure_airport") or origin_iata,
                    destination=leg.get("arrival_airport") or destination_iata,
                    departure_time=leg.get("departure_time"),
                    arrival_time=leg.get("arrival_time"),
                    duration=f"PT{dur}M" if isinstance(dur, int) else (str(dur) if dur else None),
                    stops=0,
                    cabin=cabin_class,
                    provenance="REAL_PROVIDER"
                ))
            
            if has_dur and total_duration > 0:
                h = int(total_duration) // 60
                m = int(total_duration) % 60
                duration_str = f"PT{h}H{m}M" if h > 0 else f"PT{m}M"
            else:
                duration_str = None
                
            itinerary = NormalizedItinerary(
                duration=duration_str,
                segments=segments
            )
            flight_number = segments[0].flight_number
        else:
            # This is the shape the live provider sends: one flat card, no `legs`.
            #
            # A `MarketDataController.parse_mmt_flight_string(flight.get("flight_name"))`
            # used to run here and feed `parsed_carrier` / `parsed_fl_num` into the two
            # fallbacks below. It is deleted along with the MakeMyTrip scraper it was
            # named for — see the comment where it used to live in
            # `ingestion_controller.py`. Removing it changes no observable value: the
            # `flight_name` `stdio_server.js` emits is a bare carrier name, because the
            # provider publishes no flight number, so the parse returned `("", "")` on
            # every real card and both fallbacks fell through to what they fall through
            # to now.
            from backend.services.ingestion_controller import MarketDataController

            if not primary_airline:
                primary_airline = flight.get("primary_airline") or flight.get("airline_code") or "UNKNOWN"
            if not primary_airline_name:
                primary_airline_name = flight.get("primary_airline_name") or flight.get("airline_name") or (MarketDataController.AIRLINE_NAMES.get(primary_airline) if primary_airline != "UNKNOWN" else "Unknown Carrier")

            # None if absent. Never parsed out of a display string.
            flight_number = flight.get("flight_number") or None
            dep_time = flight.get("departure_time")  # None if absent
            arr_time = flight.get("arrival_time")  # None if absent
            stops = flight.get("stops")
            raw_dur = flight.get("duration") or flight.get("duration_minutes")
            dur_str = f"PT{raw_dur}M" if isinstance(raw_dur, int) else (str(raw_dur) if raw_dur else None)
            
            segments = []
            segments.append(NormalizedSegment(
                flight_number=flight_number,
                departure_time=dep_time,
                arrival_time=arr_time,
                airline_code=primary_airline,
                airline_name=primary_airline_name,
                origin=origin_iata,
                destination=destination_iata,
                duration=dur_str,
                stops=stops,
                cabin=cabin_class,
                provenance="REAL_PROVIDER"
            ))
            
            itinerary = NormalizedItinerary(
                duration=dur_str,
                segments=segments
            )

        flight_id_str = f"{primary_airline}-{flight_number or 'RAW'}-{price}"

        return NormalizedFlight(
            id=flight_id_str,
            primary_airline=primary_airline,
            primary_airline_name=primary_airline_name,
            seats_available=seats,
            flight_number=flight_number,
            itineraries=[itinerary],
            price=price,
            # `'₹'` or `'$'` as the scraper matched it, decoded to a code — or None
            # when the card carried no price line. Never a default: this is the
            # display-side twin of the ingest screen, and it is the copy the user
            # actually sees.
            currency=decode_currency(flight.get("currency")),
            provenance="REAL_PROVIDER"
        )
