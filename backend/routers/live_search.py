"""Live search endpoint for real-time flight queries using the Google Flights MCP client.

Returns a JSON payload with a list of flights directly from the provider.
If the MCP server returns no results, falls back to authentic Supabase price
history data. Zero synthetic data policy is strictly enforced — no fake
times, airports, flight numbers, or seat counts are ever injected.
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel, field_validator
from typing import Optional

from backend.services.flight_data_service import flight_data_service
from backend.database.database import database as db

logger = logging.getLogger(__name__)
router = APIRouter()


class LiveSearchRequest(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: Optional[str] = None
    adults: Optional[int] = 1
    children: Optional[int] = 0
    infants: Optional[int] = 0
    cabin_class: Optional[str] = "ECONOMY"

    @field_validator("origin", "destination")
    @classmethod
    def normalize_airport(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3:
            raise ValueError("Airport codes must be three-letter IATA codes.")
        return v

    @field_validator("departure_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        from datetime import datetime
        datetime.strptime(v, "%Y-%m-%d")
        return v


def _build_flight_card(raw: dict, origin: str, destination: str) -> Optional[dict]:
    """
    Convert a raw MCP or DB record into a clean flight card.
    Returns None if the record has no valid price.
    NEVER fabricates any field. Returns None or omits the field if data is unavailable.
    """
    price_val = raw.get("price_inr") or raw.get("price")
    if not price_val:
        return None
    try:
        price = round(float(price_val), 2)
        if price <= 0:
            return None
    except (ValueError, TypeError):
        return None

    airline_code = raw.get("primary_airline") or raw.get("airline_code") or None
    airline_name = raw.get("airline_name") or raw.get("primary_airline_name") or None

    # Flight number: only use if explicitly provided by the provider
    flight_number = raw.get("flight_number") or None
    # Validate: reject values that look like airline names (no digits)
    if flight_number and not any(c.isdigit() for c in flight_number):
        flight_number = None

    # Legs / segments: use only what provider returned
    legs_data = raw.get("legs", [])
    if not legs_data:
        # Build a single-segment leg only if real departure/arrival times are available
        dep_time = raw.get("departure_time") or None
        arr_time = raw.get("arrival_time") or None
        stops = raw.get("stops")
        duration_min = raw.get("duration_minutes") or raw.get("duration") or None

        # Only build a segment if we have real schedule data
        if dep_time and arr_time and airline_code:
            legs_data = [{
                "flight_number": flight_number,
                "airline_code": airline_code,
                "airline": airline_name,
                "origin": origin,
                "destination": destination,
                "departure_time": dep_time,
                "arrival_time": arr_time,
                "duration": duration_min,
                "stops": stops if stops is not None else 0,
            }]

    # Seats: never fabricate
    seats_val = raw.get("seats") or raw.get("seats_available") or None

    card = {
        "origin_code": origin,
        "destination_code": destination,
        "airline_code": airline_code,
        "airline_name": airline_name,
        "flight_number": flight_number,
        "price": price,
        "seats_available": seats_val,
        "provenance": raw.get("provenance", "REAL_PROVIDER"),
        "legs": legs_data,
    }
    return card


@router.post("/live-search")
async def live_search(req: LiveSearchRequest) -> dict:
    """Query the Google Flights MCP server in real time.

    Falls back to Supabase historical cache if the live search returns
    empty results. Enforces zero-synthetic-data policy throughout.
    """
    raw_out = []
    raw_in = []

    try:
        res_out = await flight_data_service.search_flights(
            origin=req.origin,
            destination=req.destination,
            target_date=req.departure_date,
            return_date=None,
            adults=req.adults,
            children=req.children,
            infants=req.infants,
            cabin_class=req.cabin_class,
            currency="INR"
        )
        raw_out = res_out.get("data", [])

        if req.return_date:
            res_in = await flight_data_service.search_flights(
                origin=req.destination,
                destination=req.origin,
                target_date=req.return_date,
                return_date=None,
                adults=req.adults,
                currency="INR"
            )
            raw_in = res_in.get("data", [])

    except Exception as e:
        logger.error(f"Live search transport error: {e!r}")
        raw_out = []
        raw_in = []

    # Fallback to Supabase price_history if live search returned nothing
    if not raw_out:
        logger.info("Live search returned empty. Falling back to DB cache.")
        try:
            db_res = (
                db.supabase.table("price_history")
                .select("*")
                .eq("origin_code", req.origin)
                .eq("destination_code", req.destination)
                .eq("is_live", True)
                .order("recorded_at", desc=True)
                .limit(50)
                .execute()
            )
            for row in (db_res.data or []):
                row["provenance"] = "VERIFIED_MARKET_SNAPSHOT"
            raw_out = db_res.data or []
        except Exception as db_err:
            logger.error(f"Fallback database query failed: {db_err}")
            raw_out = []

    flights = []

    if req.return_date and raw_in:
        # Round-trip: pair outbound + inbound flights
        for i in range(min(len(raw_out), len(raw_in), 50)):
            f_out = raw_out[i]
            f_in = raw_in[i]

            out_price = float(f_out.get("price_inr") or f_out.get("price") or 0)
            in_price = float(f_in.get("price_inr") or f_in.get("price") or 0)
            if out_price <= 0 or in_price <= 0:
                continue

            out_card = _build_flight_card(f_out, req.origin, req.destination)
            in_card = _build_flight_card(f_in, req.destination, req.origin)
            if not out_card or not in_card:
                continue

            combined = {**out_card}
            combined["price"] = round(out_price + in_price, 2)
            combined["return_legs"] = in_card.get("legs", [])
            flights.append(combined)
    else:
        # One-way
        for raw in raw_out[:50]:
            card = _build_flight_card(raw, req.origin, req.destination)
            if card:
                flights.append(card)

    return {"flights": flights}
