"""
Amadeus Flight API Integration Service.
Handles OAuth token management and flight search.
"""

import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

AMADEUS_BASE = "https://test.api.amadeus.com"  # Use prod URL for production


class AmadeusService:
    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    async def _get_token(self) -> str:
        """Get or refresh OAuth2 token."""
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{AMADEUS_BASE}/v1/security/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.amadeus_client_id,
                    "client_secret": settings.amadeus_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._token_expires = datetime.now() + timedelta(seconds=data["expires_in"] - 60)
            return self._token

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        cabin_class: str = "ECONOMY",
        currency: str = "INR",
        max_results: int = 20,
    ) -> dict:
        """Search flights using Amadeus Flight Offers Search API."""
        token = await self._get_token()

        params = {
            "originLocationCode": origin.upper(),
            "destinationLocationCode": destination.upper(),
            "departureDate": departure_date,
            "adults": adults,
            "travelClass": cabin_class,
            "currencyCode": currency,
            "max": max_results,
            "nonStop": "false",
        }
        if return_date:
            params["returnDate"] = return_date

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{AMADEUS_BASE}/v2/shopping/flight-offers",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 400:
                logger.warning(f"Amadeus 400: {resp.text}")
                return {"data": [], "meta": {}, "dictionaries": {}}
            resp.raise_for_status()
            return resp.json()

    async def get_cheapest_dates(self, origin: str, destination: str) -> dict:
        """Get cheapest dates for a route (Flight Inspiration Search)."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{AMADEUS_BASE}/v1/shopping/flight-dates",
                params={
                    "origin": origin.upper(),
                    "destination": destination.upper(),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                return {"data": []}
            return resp.json()

    async def get_flight_inspiration(self, origin: str, currency: str = "INR") -> dict:
        """Get cheapest destinations from an origin."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{AMADEUS_BASE}/v1/shopping/flight-destinations",
                params={
                    "origin": origin.upper(),
                    "currencyCode": currency,
                    "maxPrice": 50000,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                return {"data": []}
            return resp.json()


def parse_flight_offers(raw: dict) -> list[dict]:
    """
    Parse Amadeus flight offer response into clean dicts.
    """
    offers = []
    data = raw.get("data", [])
    dictionaries = raw.get("dictionaries", {})
    carriers = dictionaries.get("carriers", {})
    aircraft_dict = dictionaries.get("aircraft", {})

    for offer in data:
        itineraries = offer.get("itineraries", [])
        price_info = offer.get("price", {})

        parsed_itineraries = []
        for itin in itineraries:
            segments = []
            for seg in itin.get("segments", []):
                dep = seg["departure"]
                arr = seg["arrival"]
                carrier_code = seg.get("carrierCode", "")
                segments.append({
                    "flight_number": f"{carrier_code}{seg.get('number', '')}",
                    "airline_code": carrier_code,
                    "airline_name": carriers.get(carrier_code, carrier_code),
                    "aircraft": aircraft_dict.get(
                        seg.get("aircraft", {}).get("code", ""), "Unknown"
                    ),
                    "origin": dep.get("iataCode"),
                    "destination": arr.get("iataCode"),
                    "departure_time": dep.get("at"),
                    "arrival_time": arr.get("at"),
                    "duration": seg.get("duration", ""),
                    "cabin": seg.get("cabin", "ECONOMY"),
                    "stops": seg.get("numberOfStops", 0),
                })
            parsed_itineraries.append({
                "duration": itin.get("duration", ""),
                "segments": segments,
            })

        offers.append({
            "id": offer.get("id"),
            "source": offer.get("source", "GDS"),
            "price": {
                "total": float(price_info.get("total", 0)),
                "base": float(price_info.get("base", 0)),
                "currency": price_info.get("currency", "INR"),
                "fees": price_info.get("fees", []),
                "grand_total": float(price_info.get("grandTotal", price_info.get("total", 0))),
            },
            "itineraries": parsed_itineraries,
            "validating_airlines": offer.get("validatingAirlineCodes", []),
            "traveler_pricings": offer.get("travelerPricings", []),
            "last_ticketing_date": offer.get("lastTicketingDate"),
            "seats_available": offer.get("numberOfBookableSeats", None),
        })

    return offers


# Singleton instance
amadeus_service = AmadeusService()
