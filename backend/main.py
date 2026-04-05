"""
SkyMind API — Main Application Entry Point
Production-ready FastAPI app with lifespan management,
CORS, all routers, and startup services.
"""

import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from rapidfuzz import fuzz
from supabase import create_client

# ── Routers ───────────────────────────────────────────────────────────
from routers import auth, alerts, booking, payment, user, prediction, flights

# ── ML ────────────────────────────────────────────────────────────────
from ml.price_model import get_predictor

# ── Services ──────────────────────────────────────────────────────────
from services.scheduler import start_scheduler

load_dotenv()

# ══════════════════════════════════════════════════════════════════════
# LIFESPAN (replaces deprecated @app.on_event)
# ══════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup → yield → Shutdown."""
    # ── Startup ───────────────────────────────────────────────────────
    print("🚀 [SkyMind] Starting background scheduler...")
    start_scheduler()

    print("🧠 [SkyMind] Loading Price Predictor model...")
    try:
        get_predictor()
        print("✅ [SkyMind] Price Predictor loaded.")
    except Exception as exc:
        print(f"⚠️  [SkyMind] Price Predictor failed to load: {exc}")

    yield  # ── App runs ─────────────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────
    print("🛑 [SkyMind] Shutting down.")


# ══════════════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="SkyMind API",
    version="10.0.0",
    description="AI-powered Flight Intelligence Platform — 2026",
    lifespan=lifespan,
)

# ══════════════════════════════════════════════════════════════════════
# CORS  — allow frontend (localhost + Vercel)
# ══════════════════════════════════════════════════════════════════════

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://localhost:3000",
]

_extra = os.getenv("CORS_ORIGINS", "")
if _extra:
    ALLOWED_ORIGINS += [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════════════
# ROUTERS
# ══════════════════════════════════════════════════════════════════════

app.include_router(auth.router,       prefix="/auth",    tags=["Auth"])
app.include_router(alerts.router,     prefix="/alerts",  tags=["Alerts"])
app.include_router(booking.router,    prefix="/booking", tags=["Booking"])
app.include_router(payment.router,    prefix="/payment", tags=["Payment"])
app.include_router(user.router,       prefix="/user",    tags=["User"])
app.include_router(prediction.router, prefix="/ai",      tags=["AI"])
app.include_router(flights.router,    prefix="/flights", tags=["Flights"])

# ══════════════════════════════════════════════════════════════════════
# SUPABASE CLIENT  (module-level singleton)
# ══════════════════════════════════════════════════════════════════════

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

if not _SUPABASE_URL or not _SUPABASE_KEY:
    raise RuntimeError("❌ Missing Supabase credentials (SUPABASE_URL / SUPABASE_SERVICE_KEY)")

supabase = create_client(_SUPABASE_URL, _SUPABASE_KEY)

# ══════════════════════════════════════════════════════════════════════
# PRICE PREDICTION ENDPOINT  (/predict  POST)
# ══════════════════════════════════════════════════════════════════════

from pydantic import BaseModel, field_validator
import math
import hashlib
import numpy as np


class PredictRequest(BaseModel):
    origin: str
    destination: str
    departure_date: str = ""

    @field_validator("origin", "destination")
    @classmethod
    def upper_strip(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("origin", "destination")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Airport code must not be empty")
        return v

    def model_post_init(self, __context):  # noqa: N802
        if self.origin == self.destination:
            raise ValueError("Origin and destination must differ")


def _deterministic_seed(origin: str, destination: str) -> int:
    raw = f"{origin}{destination}".encode()
    return int(hashlib.md5(raw).hexdigest(), 16) % (2 ** 31)


def _build_forecast(origin: str, destination: str, ai_anchor_price: float, days: int = 30) -> list[dict]:
    """
    MODIFIED: Now accepts ai_anchor_price to keep the forecast 
    aligned with the real XGBoost model.
    """
    seed = _deterministic_seed(origin, destination)
    rng = np.random.default_rng(seed)

    # Route base price now comes from the AI model
    base_price = ai_anchor_price
    slope = (rng.uniform(-0.006, 0.009)) * base_price  # per day
    phase = rng.uniform(0, 2 * math.pi)

    forecast = []
    prices = []

    for day in range(1, days + 1):
        seasonality = 0.03 * base_price * math.sin(2 * math.pi * (day + phase) / 7)
        price = base_price + slope * day + seasonality
        price = max(2800.0, price) # Domestic floor
        prices.append(price)

    std_dev = float(np.std(prices)) if len(prices) > 1 else base_price * 0.05

    for i, price in enumerate(prices, start=1):
        import datetime as dt_mod
        target_date = (dt_mod.date.today() + dt_mod.timedelta(days=i)).isoformat()

        forecast.append(
            {
                "day": i,
                "date": target_date,
                "price": round(price, 2),
                "lower": round(max(2000.0, price - std_dev), 2),
                "upper": round(price + std_dev, 2),
            }
        )

    return forecast, prices, std_dev


@app.post("/predict", tags=["Prediction"])
async def predict_price(req: PredictRequest):
    """
    Main price prediction endpoint consumed by the Next.js frontend.
    INTEGRATED: Now calls the PricePredictor model for Day 1 accuracy.
    """
    try:
        # ── 1. Call real XGBoost Model for Anchor Price ──────────────
        predictor = get_predictor()
        now = datetime.now()
        
        features = {
            "origin_code": req.origin,
            "destination_code": req.destination,
            "airline_code": "AI",
            "days_until_dep": 7.0,
            "urgency": 0.125,
            "day_of_week": now.weekday(),
            "month": now.month,
            "week_of_year": now.isocalendar()[1],
            "hour_of_day": now.hour,
            "is_peak_hour": 1 if now.hour in [8, 9, 18, 19] else 0,
            "is_live": True,
            "seats_available": 40,
            "price_change_1d": 0,
            "price_change_3d": 0,
            "demand_score": 0.5,
            "seasonality_factor": 1.0
        }
        
        ai_price = predictor.predict(features)

        # ── 2. Build Forecast around AI price ────────────────────────
        forecast, prices, std_dev = _build_forecast(req.origin, req.destination, ai_price)

        first_price = prices[0]
        last_price = prices[-1]

        # Trend
        increasing = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i-1])
        total_steps = len(prices) - 1
        prob_increase = round(increasing / total_steps, 4) if total_steps > 0 else 0.5

        if last_price > first_price * 1.05:
            trend = "RISING"
        elif last_price < first_price * 0.95:
            trend = "FALLING"
        else:
            trend = "STABLE"

        # Recommendation
        if trend == "RISING" and prob_increase > 0.6:
            recommendation = "BOOK_NOW"
            reason = "Prices are trending upward. Book now to lock in a lower fare."
        elif trend == "FALLING" and prob_increase < 0.4:
            recommendation = "WAIT"
            reason = "Prices appear to be declining. You may find a better deal soon."
        else:
            recommendation = "MONITOR"
            reason = "Prices are relatively stable. Monitor for the best opportunity."

        mean_price = float(np.mean(prices))
        confidence = float(np.clip(1 - (std_dev / mean_price), 0.50, 0.99))

        expected_change_pct = round(
            (last_price - first_price) / first_price * 100, 2
        )

        return {
            "predicted_price": round(ai_price, 2), # Using AI price here
            "forecast": forecast,
            "trend": trend,
            "probability_increase": prob_increase,
            "confidence": round(confidence, 4),
            "recommendation": recommendation,
            "reason": reason,
            "expected_change_percent": expected_change_pct,
        }

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Prediction engine error")


# ══════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["System"])
def health():
    predictor = get_predictor()
    return {
        "status": "ok",
        "model": "loaded" if predictor else "unavailable",
        "time": datetime.now(timezone.utc).isoformat(),
        "version": "10.0.0",
    }


# ══════════════════════════════════════════════════════════════════════
# AIRPORT SEARCH 
# ══════════════════════════════════════════════════════════════════════

@app.get("/airports", tags=["Airports"])
def get_airports(q: str = ""):
    try:
        q = q.strip().lower()
        if not q or len(q) < 2:
            return []

        CITY_ALIASES = {
            "bbsr": "bhubaneswar",
            "blr": "bangalore",
            "del": "delhi",
            "bom": "mumbai",
            "hyd": "hyderabad",
            "maa": "chennai",
            "ccu": "kolkata",
            "cok": "kochi",
        }
        q = CITY_ALIASES.get(q, q)

        res = (
            supabase.table("airports")
            .select("iata_code, city, name, country, state")
            .eq("is_active", True)
            .limit(200)
            .execute()
        )

        airports = res.data or []
        scored = []

        for a in airports:
            city = (a.get("city") or "").lower()
            name = (a.get("name") or "").lower()
            code = (a.get("iata_code") or "").lower()
            country = a.get("country", "")

            score = 0
            if code == q: score += 120
            if city == q: score += 110
            if city.startswith(q): score += 100
            if q in city: score += 70
            if q in name: score += 50

            score += fuzz.token_sort_ratio(q, city) * 0.3
            score += fuzz.token_sort_ratio(q, name) * 0.2

            if country == "India": score += 20
            else: score -= 10

            if score > 60: scored.append((score, a))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {
                "iata": a["iata_code"],
                "label": f'{a["city"]} ({a["iata_code"]})',
                "city": a["city"],
                "airport": a["name"],
                "country": a["country"],
                "state": a.get("state"),
            }
            for _, a in scored[:10]
        ]

    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Airport search failed")