"""SkyMind — Flights Router.

All business logic, caching, normalization, deduplication, and ML enrichment
moved to dedicated service, normalizer, repository, and formatting layers.
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Query, HTTPException

from backend.services.flight_search_service import flight_search_service
from backend.services.flight_formatter import FlightSearchFormatter
from backend.database.flight_repository import flight_repository

logger = logging.getLogger(__name__)
router = APIRouter()

CITY_TO_IATA = {
    "delhi": "DEL", "new delhi": "DEL",
    "mumbai": "BOM", "bombay": "BOM",
    "bangalore": "BLR", "bengaluru": "BLR",
    "hyderabad": "HYD",
    "chennai": "MAA", "madras": "MAA",
    "kolkata": "CCU", "calcutta": "CCU",
    "kochi": "COK", "cochin": "COK",
    "goa": "GOI",
    "ahmedabad": "AMD",
    "jaipur": "JAI",
    "lucknow": "LKO",
    "pune": "PNQ",
    "amritsar": "ATQ",
    "bhubaneswar": "BBI",
    "ranchi": "IXR",
    "patna": "PAT",
    "varanasi": "VNS",
    "dubai": "DXB",
    "london": "LHR",
    "singapore": "SIN",
    "doha": "DOH",
}


def _resolve_iata(code: str) -> str:
    if not code:
        return code
    stripped = code.strip().lower()
    return CITY_TO_IATA.get(stripped, stripped.upper())


# ══════════════════════════════════════════════════════════════════════
# GET /flights/search
# ══════════════════════════════════════════════════════════════════════

@router.get("/search")
async def search_flights(
    origin: str = Query(...),
    destination: str = Query(...),
    departure_date: str = Query(...),
    adults: int = Query(1, ge=1, le=9),
    children: int = Query(0, ge=0, le=9),
    infants: int = Query(0, ge=0, le=9),
    cabin_class: str = Query("ECONOMY"),
    max_results: int = Query(20, ge=1, le=50),
    return_date: Optional[str] = Query(None),
    sorting: str = Query("price"),
):
    origin_iata = _resolve_iata(origin)
    destination_iata = _resolve_iata(destination)

    if origin_iata == destination_iata:
        raise HTTPException(400, detail="Origin and destination cannot be the same")

    # Delegate searching, caching, normalization, ML, and sorting to the orchestration service
    presentation = await flight_search_service.search(
        origin_iata=origin_iata,
        destination_iata=destination_iata,
        departure_date=departure_date,
        adults=adults,
        children=children,
        infants=infants,
        cabin_class=cabin_class,
        max_results=max_results,
        return_date=return_date,
        sorting=sorting
    )

    # Format the canonical models into UI/LLM presentation dictionaries
    flights_formatted = [
        FlightSearchFormatter.to_presentation(f) for f in presentation.flights
    ]

    cheapest_formatted = (
        FlightSearchFormatter.to_presentation(presentation.cheapest)
        if presentation.cheapest else None
    )
    fastest_formatted = (
        FlightSearchFormatter.to_presentation(presentation.fastest)
        if presentation.fastest else None
    )
    best_value_formatted = (
        FlightSearchFormatter.to_presentation(presentation.best_value)
        if presentation.best_value else None
    )

    return {
        "flights": flights_formatted,
        "cheapest": cheapest_formatted,
        "fastest": fastest_formatted,
        "best_value": best_value_formatted,
        "recommendation": {
            "action": presentation.recommendation.action,
            "reasoning": presentation.recommendation.reasoning,
            "trend": presentation.recommendation.trend
        },
        "count": presentation.metadata.get("count", 0),
        "origin_iata": origin_iata,
        "destination_iata": destination_iata,
        "data_source": presentation.metadata.get("data_source", "UNKNOWN"),
        # Honest provenance for the client: whether these fares came from the live
        # provider or from the cache, and if the provider failed, the *kind* of
        # failure. `provider_error` is deliberately not forwarded — it carries an
        # exception repr, which belongs in the server log, not in a public response.
        "search_status": presentation.metadata.get("search_status"),
        "provider_status": presentation.metadata.get("provider_status"),
        "provider_error_kind": presentation.metadata.get("provider_error_kind"),
        "rows_persisted": presentation.metadata.get("rows_persisted"),
    }


# ══════════════════════════════════════════════════════════════════════
# GET /flights/airports
# ══════════════════════════════════════════════════════════════════════

@router.get("/airports")
async def search_airports_flights(q: str = Query(..., min_length=1)):
    q_lower = q.lower().strip()
    try:
        # Search via decoupled repository layer
        airports_data = flight_repository.search_airports(q_lower, limit=10)

        results = []
        for a in airports_data:
            results.append({
                "iata": a.get("iata_code") or a.get("iata") or "",
                "city": a.get("city") or "",
                "name": a.get("name") or "",
                "country": a.get("country") or ""
            })

        # Sort: India first, then exact code match
        results.sort(key=lambda x: (x["country"] != "India", x["iata"].lower() != q_lower))
        return {"airports": results}
    except Exception as exc:
        # This used to `return {"airports": []}` with HTTP 200, which told the client
        # "this system knows of no airport matching your query" when what actually
        # happened was that the lookup never ran. An unreachable database, a renamed
        # column, a revoked key — all of them presented as an empty result set, and an
        # empty result set from a *working* lookup is a completely ordinary answer, so
        # there was no way to tell the two apart from outside. 503 rather than 500
        # because the cause is a dependency that could not be reached, which is what
        # `predict.py` already uses that code for; the query itself was valid.
        #
        # `exc_info=True` because the old line logged `{exc}` alone, so the traceback —
        # the only thing that says *which* of those causes it was — was discarded.
        logger.error(f"Airport search failed for q={q_lower!r}: {exc}", exc_info=True)
        raise HTTPException(
            503,
            detail="Airport lookup is unavailable. This is a server-side failure, not an "
                   "empty result; please retry.",
        )
