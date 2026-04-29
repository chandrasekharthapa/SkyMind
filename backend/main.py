"""SkyMind API entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from ml.price_model import get_predictor
from routers import alerts, auth, booking, flights, payment, predict, user


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

allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "https://localhost:3000",
]
allowed_origins.extend(
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predict.router)
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(booking.router, prefix="/booking", tags=["Booking"])
app.include_router(payment.router, prefix="/payment", tags=["Payment"])
app.include_router(user.router, prefix="/user", tags=["User"])
app.include_router(flights.router, prefix="/flights", tags=["Flights"])


@app.get("/health", tags=["System"])
def health() -> dict:
    predictor = get_predictor()
    return {
        "status": "ok",
        "model": "ready" if predictor._trained else "lazy",
        "data_source": "SKYMIND_INTELLIGENCE",
        "time": datetime.now(timezone.utc).isoformat(),
        "version": "11.0.0",
    }
