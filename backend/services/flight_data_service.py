"""SkyMind flight data service - raw MCP transport layer."""
import logging
import json
import os
import asyncio
import anyio
from typing import Any, Dict, List, Optional

from backend.domain.provenance import decode_currency

try:
    from backend.services.mcp_client import get_client
except ImportError as _exc:
    # Only a missing top-level `backend` justifies retrying under the bare name
    # (the scripts in backend/ are run with cwd=backend/ and no repo root on
    # sys.path). Any other ImportError — a genuinely absent dependency inside
    # mcp_client — must propagate: retrying it here would both hide the real
    # cause and bind a second copy of this module, splitting the _shared_client
    # cache below across two singletons.
    if (_exc.name or "").split(".")[0] != "backend":
        raise
    from services.mcp_client import get_client

# Shared MCP client cache and lock for reuse
_shared_client: Any = None
_client_lock = asyncio.Lock()

async def _get_shared_client() -> Any:
    """Return a cached MCP client, creating it if necessary."""
    global _shared_client
    async with _client_lock:
        if _shared_client is None:
            _shared_client = await get_client()
        return _shared_client

logger = logging.getLogger(__name__)

# Outcome tags for FlightDataService.search_flights(). It used to return the
# literal {"data": []} for four different situations — a route with genuinely no
# flights, an unparseable provider response, an unexpected exception on the first
# attempt, and every retry exhausted — so no caller could distinguish a quiet
# market from a dead scraper. The scheduler's "zero observations" gate and the
# search service's provenance label both depend on that distinction.
STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_ERROR = "error"


def _result(
    flights: Optional[List[Any]] = None,
    status: str = STATUS_OK,
    error: Optional[str] = None,
    error_kind: Optional[str] = None,
    attempts: int = 0,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a discriminated transport result.

    `data` stays first-class and always present, so every existing caller that
    reads `res["data"]` or `res.get("data", [])` keeps working unchanged.
    """
    out: Dict[str, Any] = {
        "data": flights or [],
        "status": status,
        "error": error,
        "error_kind": error_kind,
        "attempts": attempts,
    }
    out.update(extra)
    return out


def _fx_rate(pair: str) -> Optional[float]:
    """Configured FX rate for `pair` (e.g. "USD_INR"), or None if not configured.

    There is deliberately no default. This module previously hardcoded 82.5 in
    both directions — a number with no source and no expiry, applied to fares
    that the alert checker then compared against a target the user had entered in
    rupees. An unconfigured rate means "do not convert", never a guessed one.
    """
    raw = os.getenv(f"FX_{pair}", "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        logger.error(f"FX_{pair}={raw!r} is not a number; refusing to convert.")
        return None
    if val <= 0:
        logger.error(f"FX_{pair}={raw!r} is not positive; refusing to convert.")
        return None
    return val


class FlightDataService:
    def route_supported(self, origin: str, destination: str) -> bool:
        """Check if a route is supported by the MCP tool.

        Simple case‑insensitive check; MCP will return an error for unsupported routes.
        """
        return bool(origin) and bool(destination)

    async def search_flights(
        self,
        origin: str,
        destination: str,
        target_date: str,
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
        cabin_class: str = "ECONOMY",
        max_results: int = 20,
        return_date: str | None = None,
        session: Any = None,
        currency: str = "INR",
    ) -> Dict[str, Any]:
        """Call the MCP `search_flights` tool and return genuine raw data.

        Returns a discriminated result — see `_result()`:
            status "ok"     -> the provider returned flights, in `data`
            status "empty"  -> the provider answered and this route has no flights
            status "error"  -> the transport failed; `error` and `error_kind` say how
        `data` is always present and is always a list. Absolutely no simulated data
        fallbacks: a failure returns an empty list *tagged as a failure*, never an
        empty list that reads like an answer.

        `currency` defaults to INR. It defaulted to USD, which meant the two
        callers that omit the argument — the price-alert checker in scheduler.py
        being the load-bearing one — received fares divided by an FX rate and then
        compared them against a target the user had entered in rupees, so every
        alert compared roughly 60 against roughly 5000 and fired unconditionally.
        """
        logger.info(f"Invoking live MCP search: {origin}→{destination} on {target_date}")
        max_retries = int(os.getenv("MCP_MAX_RETRIES", "3"))
        backoff = float(os.getenv("MCP_RETRY_BACKOFF", "1.0"))
        timeout = float(os.getenv("MCP_TIMEOUT", "30"))  # seconds
        attempt = 0
        last_error: Optional[str] = None
        last_kind: Optional[str] = None

        from backend.services.mcp_client import mcp_gateway

        while attempt < max_retries:
            parse_error: Optional[str] = None
            try:
                if session is not None:
                    # Use provided session
                    payload = {
                        "origin": origin.upper().strip(),
                        "destination": destination.upper().strip(),
                        "departure_date": target_date,
                        "return_date": return_date,
                        "adults": adults + children + infants,
                        "cabin_class": cabin_class,
                    }
                    target_currency = currency.upper()
                    res = await asyncio.wait_for(
                        session.call_tool("search_flights", payload),
                        timeout=timeout,
                    )
                else:
                    # Use fresh gateway for each request
                    async with mcp_gateway() as client:
                        payload = {
                            "origin": origin.upper().strip(),
                            "destination": destination.upper().strip(),
                            "departure_date": target_date,
                            "return_date": return_date,
                            "adults": adults + children + infants,
                            "cabin_class": cabin_class,
                        }
                        target_currency = currency.upper()
                        res = await asyncio.wait_for(
                            client.call_tool("search_flights", payload),
                            timeout=timeout,
                        )

                if isinstance(res, dict):
                    if "flights" in res:
                        flights = res["flights"]
                    else:
                        flights = res.get("data", [])
                elif hasattr(res, "content"):
                    try:
                        content = res.content
                        if isinstance(content, list) and content:
                            raw_text = (
                                content[0].get("text")
                                if isinstance(content[0], dict)
                                else getattr(content[0], "text", None)
                            )
                        else:
                            raw_text = getattr(res, "content", None)
                        parsed = json.loads(raw_text) if isinstance(raw_text, str) else []
                        if isinstance(parsed, dict):
                            flights = parsed.get("flights") or parsed.get("data") or []
                        elif isinstance(parsed, list):
                            flights = parsed
                        else:
                            flights = []
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse MCP TextContent: {parse_err}")
                        parse_error = f"TextContent parse failed: {parse_err}"
                        flights = []
                elif isinstance(res, str):
                    try:
                        parsed = json.loads(res)
                        if isinstance(parsed, dict):
                            flights = parsed.get("flights") or parsed.get("data") or []
                        elif isinstance(parsed, list):
                            flights = parsed
                        else:
                            flights = []
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse MCP string response: {parse_err}")
                        parse_error = f"string parse failed: {parse_err}"
                        flights = []
                else:
                    parse_error = f"unrecognised MCP response type {type(res).__name__}"
                    logger.warning(parse_error)
                    flights = []

                if parse_error:
                    # A response we could not read is a transport failure, not an
                    # empty market. It used to fall through to the [ZERO MATCHES]
                    # branch below and return the same {"data": []} as a real
                    # answer, which is how a broken scraper looked like a quiet one.
                    attempt += 1
                    last_error, last_kind = parse_error, "parse"
                    if attempt < max_retries:
                        await asyncio.sleep(backoff * (2 ** (attempt - 1)))
                        continue
                    logger.error(f"MCP response unreadable after {attempt} attempt(s): {parse_error}")
                    return _result(status=STATUS_ERROR, error=parse_error,
                                   error_kind="parse", attempts=attempt)

                if not flights:
                    logger.info(f"[ZERO MATCHES] No flights for {origin}-{destination} {target_date}")
                    return _result(status=STATUS_EMPTY, attempts=attempt + 1)
                # Currency conversion. Applied only when a rate is configured; an
                # unset rate leaves the fare in the currency the provider quoted and
                # says so, rather than converting at a hardcoded 82.5.
                converted = 0
                unconverted: Dict[str, int] = {}
                undeclared = 0
                for f in flights:
                    if not (isinstance(f, dict) and "price" in f):
                        continue
                    f_price = f.get("price")
                    # `(f.get("currency") or "INR").upper()` used to be here, and it
                    # is the same fabrication as `format_payload`'s old default: a
                    # fare of unknown denomination was declared to be in rupees, so
                    # the loop concluded it already matched the target currency and
                    # skipped it. Absent is now unknown — no conversion can be
                    # justified for it, and the write path refuses it rather than
                    # storing a number whose unit nobody knows.
                    f_curr = decode_currency(f.get("currency"))
                    if f_curr is None:
                        undeclared += 1
                        continue
                    if f_price is None or f_curr == target_currency:
                        continue
                    try:
                        f_price_val = float(f_price)
                    except (ValueError, TypeError):
                        continue

                    rate = _fx_rate(f"{f_curr}_{target_currency}")
                    inverse = _fx_rate(f"{target_currency}_{f_curr}")
                    if rate is not None:
                        f["price"] = round(f_price_val * rate, 2)
                        f["currency"] = target_currency
                        converted += 1
                    elif inverse is not None:
                        f["price"] = round(f_price_val / inverse, 2)
                        f["currency"] = target_currency
                        converted += 1
                    else:
                        key = f"{f_curr}->{target_currency}"
                        unconverted[key] = unconverted.get(key, 0) + 1

                for pair, n in unconverted.items():
                    logger.error(
                        f"No FX rate configured for {pair} (set FX_{pair.replace('->', '_')}); "
                        f"{n} fare(s) left in the quoted currency."
                    )
                if undeclared:
                    logger.error(
                        f"{undeclared} of {len(flights)} fare(s) arrived with no readable "
                        f"currency; they are left unconverted and will be refused at "
                        f"ingest rather than stored as {target_currency}."
                    )

                return _result(
                    flights, status=STATUS_OK, attempts=attempt + 1,
                    requested_currency=target_currency,
                    converted=converted,
                    unconverted=unconverted or None,
                    undeclared_currency=undeclared or None,
                )
            except anyio.ClosedResourceError as e:
                attempt += 1
                last_error, last_kind = repr(e), "transport"
                logger.warning(
                    f"Live MCP search failed with ClosedResourceError (attempt {attempt}/{max_retries}): {e!r}. Retrying after {backoff}s"
                )
                if attempt >= max_retries:
                    break
                await asyncio.sleep(backoff * (2 ** (attempt - 1)))
                continue
            except asyncio.TimeoutError:
                attempt += 1
                last_error, last_kind = f"timed out after {timeout}s", "timeout"
                logger.warning(
                    f"Live MCP search timed out after {timeout}s (attempt {attempt}/{max_retries}). Retrying..."
                )
                if attempt >= max_retries:
                    break
                await asyncio.sleep(backoff * (2 ** (attempt - 1)))
                continue
            except Exception as e:
                # This used to `return {"data": []}` immediately: an unexpected
                # exception on the first attempt was reported as "no flights on this
                # route", it never reached the retry loop the two handlers above use,
                # and the caller could not tell it apart from a real empty result.
                # Treat it as a retryable transport failure like the others, and if
                # the retries run out, say what happened.
                import traceback
                attempt += 1
                last_error, last_kind = repr(e), "unexpected"
                logger.error(f"Live MCP search failed (attempt {attempt}/{max_retries}): {e!r}")
                logger.error(traceback.format_exc())
                if attempt >= max_retries:
                    break
                await asyncio.sleep(backoff * (2 ** (attempt - 1)))
                continue

        logger.error(
            f"Live MCP search failed after {attempt} attempt(s) "
            f"[{last_kind}]: {last_error}"
        )
        return _result(status=STATUS_ERROR, error=last_error or "retries exhausted",
                       error_kind=last_kind or "exhausted", attempts=attempt)


flight_data_service = FlightDataService()
