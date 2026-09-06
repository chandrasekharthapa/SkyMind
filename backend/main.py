"""SkyMind API entry point."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.ml.price_model import get_predictor
from backend.routers import alerts, auth, booking, flights, payment, predict, user, live_search, chat, system


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_predictor()
    yield


app = FastAPI(
    title="SkyMind - Multi-Agent Flight Intelligence API",
    version="11.0.0",
    description="Self-contained proprietary flight intelligence with ML forecasting and deterministic agents.",
    lifespan=lifespan,
)

SKYMIND_ENV = os.getenv("SKYMIND_ENV", "development").strip().lower()
IS_PRODUCTION = SKYMIND_ENV == "production"

# Deployed frontends are named here, never in the source.
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

# Loopback origins on ANY port, in development only. The list here used to be five
# hardcoded entries — 3000, 3001, 3002 on localhost plus 127.0.0.1:3000 — and
# `npm run dev` moves to 3003, 3004 and upward whenever a port is taken, so the
# frontend broke the moment it landed outside those three. The failure is silent
# from the server's side: Starlette answers a preflight from an unlisted origin
# with a bare 400 and the reason ("Disallowed CORS origin") only ever appears in
# the browser console, which is why the log below now records the origin on 4xx.
# In production this regex is None and an unnamed origin is refused.
allowed_origin_regex = None if IS_PRODUCTION else r"https?://(localhost|127\.0\.0\.1|\[::1\]):\d+"

if IS_PRODUCTION and not allowed_origins:
    logging.getLogger("skymind").warning(
        "SKYMIND_ENV=production and CORS_ORIGINS is empty: every cross-origin "
        "browser request will be refused. Set CORS_ORIGINS to the deployed "
        "frontend's origin."
    )

app.add_middleware(GZipMiddleware, minimum_size=1000)

# This previously passed allow_origins=["*"] together with allow_credentials=True,
# which Starlette resolves by echoing the caller's Origin header back — so any
# website could make credentialed cross-origin requests to this API. Widen the
# CORS_ORIGINS env var (comma-separated), never these arguments.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

logger = logging.getLogger("skymind_observability")

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "latency_seconds": round(process_time, 4),
        "client_host": request.client.host if request.client else "unknown"
    }
    
    if response.status_code >= 400:
        # A refused CORS preflight is a bare 400 from CORSMiddleware. Starlette does
        # put the reason in the body — "Disallowed CORS origin" / "method" /
        # "headers" — but a preflight body is never surfaced by the browser, so the
        # only trace anywhere was `OPTIONS ... 400` in this log, which names no
        # cause. Record the origin, and for a preflight the method and headers it
        # asked for, so the next failure diagnoses itself.
        log_data["origin"] = request.headers.get("origin")
        if request.method == "OPTIONS":
            log_data["cors_request_method"] = request.headers.get("access-control-request-method")
            log_data["cors_request_headers"] = request.headers.get("access-control-request-headers")
        logger.warning(json.dumps(log_data))
    elif any(p in request.url.path for p in ["predict", "system", "validation", "health"]):
        logger.info(json.dumps(log_data))

    return response

app.include_router(predict.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1/system")
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(booking.router, prefix="/booking", tags=["Booking"])
app.include_router(payment.router, prefix="/payment", tags=["Payment"])
app.include_router(user.router, prefix="/user", tags=["User"])
app.include_router(flights.router, prefix="/flights", tags=["Flights"])
app.include_router(live_search.router, tags=["LiveSearch"])
app.include_router(chat.router, prefix="/api")


from fastapi.responses import JSONResponse
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
                "details": None
            }
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": exc.errors()
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(exc),
                "details": None
            }
        }
    )

@app.get("/health", tags=["System"])
async def health() -> dict:
    """The unprefixed liveness probe, delegating to the one implementation.

    This was a second copy of `routers/system.get_health` — same fields, same
    hardcoded `"status": "ok"`, plus a `"version"` key the other does not have.
    Two health endpoints that can disagree is worse than either alone: Render's
    health check points at this one, so the copy that decided whether a deploy was
    considered live was not the copy anything else read. It delegates now, and adds
    only the extra key.
    """
    payload = await system.get_health()
    payload["version"] = payload["backend_version"]
    return payload
