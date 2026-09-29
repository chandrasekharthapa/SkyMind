"""Honest live Google Flights search with provenance-safe cache fallback."""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.database.database import database as db
from backend.domain.provenance import PROVENANCE_IS_FILTERS, decode_currency
from backend.services.flight_data_service import (
    STATUS_EMPTY,
    STATUS_ERROR,
    STATUS_OK,
    flight_data_service,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class LiveSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str
    destination: str
    departure_date: str
    return_date: Optional[str] = None
    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=9)
    infants: int = Field(default=0, ge=0, le=9)
    cabin_class: str = "ECONOMY"

    @field_validator("origin", "destination")
    @classmethod
    def normalize_airport(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("Airport codes must be three-letter IATA codes.")
        return value

    @field_validator("departure_date", "return_date")
    @classmethod
    def validate_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError):
            raise ValueError("Date must be a valid ISO calendar date (YYYY-MM-DD)") from None

    @field_validator("cabin_class")
    @classmethod
    def validate_cabin(cls, value: str) -> str:
        value = value.strip().upper()
        allowed = {"ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"}
        if value not in allowed:
            raise ValueError(f"cabin_class must be one of {sorted(allowed)}")
        return value

    @model_validator(mode="after")
    def validate_search(self):
        if self.origin == self.destination:
            raise ValueError("Origin and destination cannot be the same")
        if not 1 <= self.adults <= 9:
            raise ValueError("adults must be from 1 to 9")
        if not 0 <= self.children <= 9 or not 0 <= self.infants <= 9:
            raise ValueError("children and infants must be from 0 to 9")
        if self.infants > self.adults:
            raise ValueError("Infants cannot exceed adults")
        if self.adults + self.children + self.infants > 9:
            raise ValueError("Total passengers cannot exceed 9")
        if self.return_date and self.return_date < self.departure_date:
            raise ValueError("return_date cannot precede departure_date")
        return self


def _build_flight_card(
    raw: dict,
    origin: str,
    destination: str,
    *,
    provenance: str,
) -> Optional[dict]:
    """Map only values present in an authentic provider or cache record."""
    price_val = raw.get("price_inr") or raw.get("price")
    try:
        price = round(float(price_val), 2)
    except (ValueError, TypeError):
        return None
    if price <= 0:
        return None

    currency = decode_currency(raw.get("currency"))
    airline_code = raw.get("primary_airline") or raw.get("airline_code") or None
    airline_name = raw.get("airline_name") or raw.get("primary_airline_name") or None
    flight_number = raw.get("flight_number") or None
    if flight_number and not any(char.isdigit() for char in str(flight_number)):
        flight_number = None

    legs_data = raw.get("legs") if isinstance(raw.get("legs"), list) else []
    if not legs_data:
        departure = raw.get("departure_time")
        arrival = raw.get("arrival_time")
        if departure and arrival and airline_code:
            legs_data = [{
                "flight_number": flight_number,
                "airline_code": airline_code,
                "airline": airline_name,
                "origin": origin,
                "destination": destination,
                "departure_time": departure,
                "arrival_time": arrival,
                "duration": raw.get("duration_minutes") or raw.get("duration"),
                "stops": raw.get("stops"),
            }]

    return {
        "origin_code": origin,
        "destination_code": destination,
        "airline_code": airline_code,
        "airline_name": airline_name,
        "flight_number": flight_number,
        "price": price,
        "currency": currency,
        "seats_available": raw.get("seats") or raw.get("seats_available") or None,
        "provenance": provenance,
        "legs": legs_data,
    }


def _cache_rows(origin: str, destination: str, departure_date: str) -> list[dict]:
    query = (
        db.supabase.table("price_history")
        .select("*")
        .eq("origin_code", origin)
        .eq("destination_code", destination)
        .eq("departure_date", departure_date)
    )
    for column, value in PROVENANCE_IS_FILTERS:
        query = query.is_(column, value)
    result = query.order("recorded_at", desc=True).limit(50).execute()
    return result.data or []


async def _search_leg(
    origin: str,
    destination: str,
    departure_date: str,
    request: LiveSearchRequest,
) -> dict:
    result = await flight_data_service.search_flights(
        origin=origin,
        destination=destination,
        target_date=departure_date,
        return_date=None,
        adults=request.adults,
        children=request.children,
        infants=request.infants,
        cabin_class=request.cabin_class,
        max_results=50,
        currency="INR",
    )
    if not isinstance(result, dict) or result.get("status") not in {
        STATUS_OK, STATUS_EMPTY, STATUS_ERROR
    }:
        return {
            "data": [], "status": STATUS_ERROR, "error_kind": "contract",
            "error": "flight transport returned an invalid result",
        }
    return result


@router.post("/live-search")
async def live_search(req: LiveSearchRequest) -> dict:
    """Return one-way offers; never manufacture a round-trip itinerary."""
    if req.return_date:
        # Reject before invoking the provider. Independently searching two legs
        # and pairing rows by list index manufactured an itinerary Google never
        # offered; an unsupported request must not incur a live scrape either.
        raise HTTPException(
            status_code=501,
            detail=(
                "Round-trip live search is unavailable until provider-confirmed "
                "round-trip itineraries can be returned without pairing independent legs."
            ),
        )

    outbound = await _search_leg(
        req.origin, req.destination, req.departure_date, req
    )
    provider_status = outbound["status"]

    # Data accompanying an error status is not trusted. A failed transport may
    # have accumulated a partial response, but presenting it as a successful live
    # result would erase the failure distinction the transport contract provides.
    provider_rows = outbound.get("data") if provider_status == STATUS_OK else []
    if not isinstance(provider_rows, list):
        provider_rows = []

    cards = [
        card
        for raw in provider_rows[:50]
        if isinstance(raw, dict)
        and (card := _build_flight_card(
            raw, req.origin, req.destination,
            provenance="LIVE_GOOGLE_FLIGHTS",
        )) is not None
    ]
    data_source = "live_provider" if cards else None
    cache_error = None

    if not cards:
        try:
            cache_rows = _cache_rows(
                req.origin, req.destination, req.departure_date
            )
            cards = [
                card
                for raw in cache_rows[:50]
                if isinstance(raw, dict)
                and (card := _build_flight_card(
                    raw, req.origin, req.destination,
                    provenance="AUTHENTIC_PRICE_HISTORY",
                )) is not None
            ]
            if cards:
                data_source = "cache"
        except Exception as exc:
            cache_error = type(exc).__name__
            logger.error("Live-search cache query failed: %s", exc, exc_info=True)

    if cards:
        # Cache data can keep the endpoint useful during a provider outage, but it
        # cannot turn that outage into an unqualified success.
        status = "degraded" if provider_status == STATUS_ERROR else "ok"
    elif provider_status == STATUS_ERROR:
        # A successful cache query returning zero rows does not disprove the live
        # transport failure. Preserve error rather than reporting a quiet market.
        status = "error"
    else:
        status = "empty"

    return {
        "flights": cards,
        "status": status,
        "provider_status": provider_status,
        "provider_error_kind": outbound.get("error_kind"),
        "provider_attempts": outbound.get("attempts", 0),
        "data_source": data_source,
        "cache_error_kind": cache_error,
    }
