"""Chatbot Tool Registry.

Defines deterministic tool executions mapping directly to core SkyMind services.
No direct database clients or synthetic features are used.
"""

import asyncio
import inspect
import logging
from datetime import date, datetime
from typing import Dict, Any, Optional, List, Tuple
from zoneinfo import ZoneInfo
import numpy as np

from backend.services.flight_search_service import flight_search_service
from backend.services.prediction_service import prediction_service
from backend.services.recommendation_engine import RecommendationEngine
from backend.database.flight_repository import flight_repository
from backend.services.flight_data_service import flight_data_service
from backend.services.flight_normalizer import FlightNormalizer, NormalizedFlight, NormalizedItinerary, NormalizedSegment
from backend.domain.provenance import decode_currency

logger = logging.getLogger(__name__)


def _presentation_to_flights(res) -> List[Dict[str, Any]]:
    """Convert FlightSearchPresentation or list to a JSON-safe list of flight dicts."""
    if res is None:
        return []
    # Pydantic model (FlightSearchPresentation)
    if hasattr(res, "flights"):
        flights = res.flights
        result = []
        for f in flights:
            if hasattr(f, "model_dump"):
                result.append(f.model_dump())
            elif hasattr(f, "dict"):
                result.append(f.dict())
            elif isinstance(f, dict):
                result.append(f)
        return result
    # Already a list
    if isinstance(res, list):
        return [
            (f.model_dump() if hasattr(f, "model_dump") else f.dict() if hasattr(f, "dict") else f)
            for f in res
        ]
    return []


class SearchFlightsTool:
    @staticmethod
    async def run(origin: str, destination: str, departure_date: str, cabin_class: str = "ECONOMY") -> Dict[str, Any]:
        """Wrap FlightSearchService search execution."""
        try:
            res = await flight_search_service.search(
                origin_iata=origin,
                destination_iata=destination,
                departure_date=departure_date,
                adults=1,
                cabin_class=cabin_class,
                sorting="price"
            )
            flights = _presentation_to_flights(res)
            metadata = res.metadata if hasattr(res, "metadata") else {}
            return {"status": "success", "flights": flights, "metadata": metadata}
        except Exception as e:
            logger.error(f"SearchFlightsTool execution failed: {e}")
            return {"status": "error", "message": str(e)}

class PricePredictionTool:
    @staticmethod
    async def run(origin: str, destination: str, departure_date: str, airline_code: Optional[str] = None) -> Dict[str, Any]:
        """Wrap PredictionService predict execution."""
        try:
            res = await prediction_service.predict(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                airline_code=airline_code
            )
            return {"status": "success", **res}
        except Exception as e:
            logger.error(f"PricePredictionTool execution failed: {e}")
            return {"status": "error", "message": str(e)}

class ForecastPricesTool:
    @staticmethod
    async def run(origin: str, destination: str, departure_date: str, airline_code: Optional[str] = None) -> Dict[str, Any]:
        """Wrap PredictionService forecast extraction."""
        try:
            res = await prediction_service.predict(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                airline_code=airline_code
            )
            return {"status": "success", "forecast": res.get("forecast", [])}
        except Exception as e:
            logger.error(f"ForecastPricesTool execution failed: {e}")
            return {"status": "error", "message": str(e)}

class RecommendFlightsTool:
    @staticmethod
    async def run(origin: str, destination: str, departure_date: str, cabin_class: str = "ECONOMY") -> Dict[str, Any]:
        """Uses RecommendationEngine to determine Cheapest, Fastest, and Best Value options."""
        try:
            # 1. Search options
            presentation = await flight_search_service.search(
                origin_iata=origin,
                destination_iata=destination,
                departure_date=departure_date,
                adults=1,
                cabin_class=cabin_class,
                sorting="price"
            )
            search_res = _presentation_to_flights(presentation)
            if not search_res:
                return {"status": "success", "cheapest": None, "fastest": None, "best_value": None}

            # 2. Reconstruct NormalizedFlight models from search presentation dicts.
            #
            # Every `or "<literal>"` fallback that used to fill these fields has been
            # removed. NormalizedSegment declares flight_number, departure_time,
            # arrival_time, airline_code, airline_name and duration as
            # `Optional[...] = None` specifically so an unknown attribute can travel
            # as unknown; filling them with "1000", noon/2pm timestamps, "6E"/"IndiGo"
            # and "PT2H" made the chatbot assert flight numbers, departure times,
            # carriers and durations that no provider ever returned.
            #
            # "PT2H" was the most damaging: get_duration_minutes() returns the 9999
            # sentinel for an absent duration, so a flight of unknown length can never
            # win "fastest" — and "PT2H" overrode that sentinel with a flat 120
            # minutes, which is short enough to win. The recommendation was then
            # derived from the fabricated number.
            normalized_flights = []
            dropped: Dict[str, int] = {}
            for idx, f in enumerate(search_res):
                price_data = f.get("price")
                price_val = price_data.get("total") if isinstance(price_data, dict) else price_data
                # Decoded from what the search actually returned. This read
                # `(price_data.get("currency") or "INR") ... else "INR"` until
                # AUDIT-FIXES.md §48, which re-stamped rupees on the chatbot's own
                # copy of a fare the search layer had already refused to label —
                # a fabrication reinstated one layer downstream of its fix.
                currency_val = (
                    decode_currency(price_data.get("currency"))
                    if isinstance(price_data, dict) else None
                )

                # primary_airline and primary_airline_name are the only required `str`
                # fields on NormalizedFlight, so an option with no carrier cannot be
                # represented. Drop it and say so, rather than labelling it IndiGo.
                carrier = f.get("primary_airline") or f.get("airline_code")
                carrier_name = f.get("primary_airline_name") or carrier

                reason = None
                if price_val is None:
                    reason = "no price"
                elif not carrier:
                    reason = "no carrier"
                if reason:
                    dropped[reason] = dropped.get(reason, 0) + 1
                    continue

                itins = []
                for itin in f.get("itineraries", []):
                    segs = []
                    for seg in itin.get("segments", []):
                        segs.append(NormalizedSegment(
                            flight_number=seg.get("flight_number"),
                            departure_time=seg.get("departure_time"),
                            arrival_time=seg.get("arrival_time"),
                            airline_code=seg.get("carrier_code") or seg.get("airline_code") or carrier,
                            airline_name=seg.get("carrier_name") or seg.get("airline_name") or carrier_name,
                            origin=seg.get("origin_code") or seg.get("origin") or origin,
                            destination=seg.get("destination_code") or seg.get("destination") or destination,
                            duration=itin.get("duration"),
                            stops=len(itin.get("segments", [])) - 1,
                            cabin=cabin_class
                        ))
                    itins.append(NormalizedItinerary(
                        duration=itin.get("duration"),
                        segments=segs
                    ))
                
                norm = NormalizedFlight(
                    id=str(f.get("id") or f"{carrier}-{f.get('flight_number') or 'UNKNOWN'}-{price_val}"),
                    primary_airline=carrier,
                    primary_airline_name=carrier_name,
                    seats_available=f.get("seats_available"),
                    flight_number=f.get("flight_number"),
                    itineraries=itins,
                    price=float(price_val),
                    currency=currency_val,
                    # Position of the source dict, so the highlights below map back
                    # exactly. Matching on flight_number was wrong twice over: it is
                    # now legitimately None for unidentified flights, so the first
                    # None-numbered option would win every lookup — and the old "1000"
                    # fallback gave several distinct flights the same number, which
                    # made the same lookup return an arbitrary one of them.
                    metadata={"source_index": idx}
                )
                normalized_flights.append(norm)

            for reason, n in dropped.items():
                logger.warning(
                    f"RecommendFlightsTool: dropped {n} option(s) with {reason} for "
                    f"{origin}-{destination} {departure_date}; not inferable from the response."
                )

            if not normalized_flights:
                return {"status": "success", "cheapest": None, "fastest": None, "best_value": None}

            # 3. Highlight options
            cheapest, fastest, best_val = RecommendationEngine.identify_highlights(normalized_flights)

            def _source_dict(nf: Optional[NormalizedFlight]) -> Optional[Dict[str, Any]]:
                """Map a highlighted flight back to the exact dict it was built from."""
                if nf is None:
                    return None
                i = (nf.metadata or {}).get("source_index")
                if isinstance(i, int) and 0 <= i < len(search_res):
                    return search_res[i]
                return None

            return {
                "status": "success",
                "cheapest": _source_dict(cheapest),
                "fastest": _source_dict(fastest),
                "best_value": _source_dict(best_val)
            }
        except Exception as e:
            logger.error(f"RecommendFlightsTool execution failed: {e}")
            return {"status": "error", "message": str(e)}

class CompareFlightsTool:
    @staticmethod
    async def run(origin: str, destination: str, departure_date: str, cabin_class: str = "ECONOMY") -> Dict[str, Any]:
        """Compare options side-by-side."""
        try:
            res = await flight_search_service.search(
                origin_iata=origin,
                destination_iata=destination,
                departure_date=departure_date,
                adults=1,
                cabin_class=cabin_class,
                sorting="price"
            )
            flights = _presentation_to_flights(res)
            return {"status": "success", "flights": flights[:3]}  # Return top 3 options
        except Exception as e:
            logger.error(f"CompareFlightsTool execution failed: {e}")
            return {"status": "error", "message": str(e)}

class AirportInformationTool:
    @staticmethod
    def run(query: str) -> Dict[str, Any]:
        """Query airport metadata from repository."""
        try:
            airports = flight_repository.search_airports(query)
            return {"status": "success", "airports": airports}
        except Exception as e:
            logger.error(f"AirportInformationTool execution failed: {e}")
            return {"status": "error", "message": str(e)}

class RouteInformationTool:
    @staticmethod
    def run(origin: str, destination: str) -> Dict[str, Any]:
        """Verify flight routes support."""
        try:
            supported = flight_data_service.route_supported(origin.upper(), destination.upper())
            return {"status": "success", "origin": origin, "destination": destination, "supported": supported}
        except Exception as e:
            logger.error(f"RouteInformationTool execution failed: {e}")
            return {"status": "error", "message": str(e)}

class HistoricalPricesTool:
    @staticmethod
    def run(origin: str, destination: str, departure_date: str) -> Dict[str, Any]:
        """Fetch historical price ranges from database price cache."""
        try:
            history = flight_repository.get_price_history_cache(origin, destination, departure_date, 10)
            return {"status": "success", "data": history}
        except Exception as e:
            logger.error(f"HistoricalPricesTool execution failed: {e}")
            return {"status": "error", "message": str(e)}


# ── Registry Execution Map ────────────────────────────────────────────

TOOL_MAP = {
    "search_flights": SearchFlightsTool,
    "predict_price": PricePredictionTool,
    "forecast_prices": ForecastPricesTool,
    "recommend_flights": RecommendFlightsTool,
    "compare_flights": CompareFlightsTool,
    "airport_information": AirportInformationTool,
    "route_information": RouteInformationTool,
    "historical_prices": HistoricalPricesTool
}

# Fields the chat service fills from the conversation when a tool call omits them.
CONTEXT_FIELDS = ("origin", "destination", "departure_date")
_IST = ZoneInfo("Asia/Kolkata")


def accepted_params(name: str) -> Optional[set]:
    """The keyword arguments a registered tool's run() accepts, or None if unknown."""
    tool_cls = TOOL_MAP.get(name)
    if not tool_cls or not hasattr(tool_cls, "run"):
        return None
    return {
        p.name for p in inspect.signature(tool_cls.run).parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }


def prepare_tool_args(name: str, args: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    """Clean an LLM-produced argument dict for `name`.

    Returns (args, error). The model's arguments were passed straight to
    run(**args), so any key the tool does not take — an "adults" the model
    added, or the origin/destination/departure_date the chat service merged in
    from earlier turns — raised TypeError. That made airport_information and
    route_information fail on every turn after the first route search, because
    the merged context always carried a departure_date they do not accept.

    Also normalises what the model commonly gets almost right: city names for
    airport codes ("Delhi" -> "DEL"), relative dates ("tomorrow"), and lower
    case. A date that is malformed or already past (in India time — the fares
    are Indian domestic) is returned as an error the model can relay, instead of
    sending the scraper after a flight that has left.
    """
    from backend.services.intent_planner import normalize_airport_code, normalize_relative_date

    allowed = accepted_params(name)
    cleaned = {k: v for k, v in (args or {}).items() if allowed is None or k in allowed}

    for key in ("origin", "destination"):
        if key in cleaned:
            raw = cleaned[key]
            code = normalize_airport_code(str(raw)) if raw is not None else None
            if not code:
                return cleaned, (
                    f"'{raw}' is not a recognised airport. Ask the user for the city or its "
                    "3-letter IATA code."
                )
            cleaned[key] = code

    if "airline_code" in cleaned:
        code = str(cleaned["airline_code"] or "").strip().upper()
        if code:
            cleaned["airline_code"] = code
        else:
            cleaned.pop("airline_code")

    if "cabin_class" in cleaned:
        cabin = str(cleaned["cabin_class"] or "ECONOMY").strip().upper().replace(" ", "_")
        cleaned["cabin_class"] = cabin if cabin in {"ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"} else "ECONOMY"

    if "departure_date" in cleaned:
        raw = cleaned["departure_date"]
        iso = normalize_relative_date(str(raw), datetime.now(_IST)) if raw else None
        try:
            parsed = date.fromisoformat(iso) if iso else None
        except ValueError:
            parsed = None
        if parsed is None:
            return cleaned, (
                f"'{raw}' is not a valid departure date. Ask the user for a date (YYYY-MM-DD)."
            )
        if parsed < datetime.now(_IST).date():
            return cleaned, (
                f"{parsed.isoformat()} is in the past. Ask the user for a future departure date."
            )
        cleaned["departure_date"] = parsed.isoformat()

    return cleaned, None


async def execute_chatbot_tool(name: str, args: dict) -> Dict[str, Any]:
    """Dynamically route execution to target registered tool wrapper."""
    tool_cls = TOOL_MAP.get(name)
    if not tool_cls:
        logger.warning(f"Unregistered tool invoked: {name}")
        return {"status": "error", "message": f"Tool '{name}' is not registered."}

    clean_args, problem = prepare_tool_args(name, args)
    if problem:
        return {"status": "error", "message": problem}

    try:
        if inspect.iscoroutinefunction(tool_cls.run):
            return await tool_cls.run(**clean_args)
        # The synchronous tools make blocking Supabase calls; run them off the
        # event loop so one chat turn does not stall every other request.
        return await asyncio.to_thread(tool_cls.run, **clean_args)
    except TypeError as e:
        # A required argument is missing. Tell the model what to ask for.
        logger.warning(f"Tool {name} called with incomplete args {sorted(clean_args)}: {e}")
        return {"status": "error", "message": f"Missing information for {name}: {e}. Ask the user for it."}
    except Exception as e:
        logger.error(f"Failed executing tool {name} with args {clean_args}: {e}")
        return {"status": "error", "message": str(e)}
