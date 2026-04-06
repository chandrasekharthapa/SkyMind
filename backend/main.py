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

# ── Routers ───────────────────────────────────────────
from routers import auth, alerts, booking, payment, user, prediction, flights

# ── ML ────────────────────────────────────────────────
from ml.price_model import get_predictor

# ── Services ──────────────────────────────────────────
from services.scheduler import start_scheduler

load_dotenv()

# ══════════════════════════════════════════════════════
# LIFESPAN
# ══════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 [SkyMind] Starting background scheduler...")
    start_scheduler()

    print("🧠 [SkyMind] Loading Price Predictor model...")
    try:
        get_predictor()
        print("✅ [SkyMind] Price Predictor loaded.")
    except Exception as exc:
        print(f"⚠️  [SkyMind] Price Predictor failed to load: {exc}")

    yield

    print("🛑 [SkyMind] Shutting down.")


# ══════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════

app = FastAPI(
    title="SkyMind API",
    version="10.0.0",
    description="AI-powered Flight Intelligence Platform — 2026",
    lifespan=lifespan,
)

# ══════════════════════════════════════════════════════
# CORS
# ══════════════════════════════════════════════════════

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://localhost:3000",
    "https://your-app.vercel.app"
    
]

_extra = os.getenv("CORS_ORIGINS", "")
if _extra:
    ALLOWED_ORIGINS += [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex="https://skymind-gray.vercel.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════
# ROUTERS
# ══════════════════════════════════════════════════════

app.include_router(auth.router,       prefix="/auth",    tags=["Auth"])
app.include_router(alerts.router,     prefix="/alerts",  tags=["Alerts"])
app.include_router(booking.router,    prefix="/booking", tags=["Booking"])
app.include_router(payment.router,    prefix="/payment", tags=["Payment"])
app.include_router(user.router,       prefix="/user",    tags=["User"])
app.include_router(prediction.router, prefix="/ai",      tags=["AI"])
app.include_router(flights.router,    prefix="/flights", tags=["Flights"])

# ══════════════════════════════════════════════════════
# SUPABASE
# ══════════════════════════════════════════════════════

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

if not _SUPABASE_URL or not _SUPABASE_KEY:
    raise RuntimeError("❌ Missing Supabase credentials")

supabase = create_client(_SUPABASE_URL, _SUPABASE_KEY)

# ══════════════════════════════════════════════════════
# REQUEST MODEL
# ══════════════════════════════════════════════════════

from pydantic import BaseModel, field_validator


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

    def model_post_init(self, __context):
        if self.origin == self.destination:
            raise ValueError("Origin and destination must differ")


# ══════════════════════════════════════════════════════
# ✅ FINAL /predict (CLEAN — NO OLD LOGIC)
# ══════════════════════════════════════════════════════

@app.post("/predict", tags=["Prediction"])
async def predict_price(req: PredictRequest):
    try:
        from routers.prediction import predict_price_get

        return await predict_price_get(
            origin=req.origin,
            destination=req.destination,
            departure_date=req.departure_date,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════════════════

@app.get("/health", tags=["System"])
def health():
    predictor = get_predictor()
    return {
        "status": "ok",
        "model": "loaded" if predictor else "unavailable",
        "time": datetime.now(timezone.utc).isoformat(),
        "version": "10.0.0",
    }


# ══════════════════════════════════════════════════════
# AIRPORT SEARCH
# ══════════════════════════════════════════════════════

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