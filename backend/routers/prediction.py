"""
SkyMind — AI Price Prediction Router  (/ai/price)
Updated to match 2026 Weighted ML Logic.
"""

import traceback
from datetime import datetime, date, timedelta

import numpy as np
import pytz

from fastapi import APIRouter, HTTPException
from ml.price_model import get_predictor
from database.database import database as db

router = APIRouter()

IST = pytz.timezone("Asia/Kolkata")

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _adjust_prediction(price: float) -> float:
    """Clamp to 2026 domestic price range (matches floor/ceiling logic)."""
    return round(max(2800.0, min(45_000.0, price)), 2)


def _get_recent_prices(origin: str, destination: str) -> list[float]:
    try:
        # Optimized to pull from history for real-time market blending
        res = (
            db.supabase.table("price_history")
            .select("price")
            .eq("origin_code", origin)
            .eq("destination_code", destination)
            .order("recorded_at", desc=True)
            .limit(10)
            .execute()
        )
        return [float(r["price"]) for r in (res.data or [])]
    except Exception:
        return []


def _get_market_median(prices: list[float]) -> float | None:
    if not prices:
        return None
    return float(np.median(prices))


def _calculate_confidence(recent_count: int, volatility: float) -> float:
    # 2026 Confidence Algorithm
    base = min(recent_count / 15, 1) * 65
    stability = max(0.0, 30 - (volatility / 1500))
    return round(max(25.0, min(98.0, base + stability)), 2)


def _get_smart_recommendation(current: float, predicted: float, confidence: float) -> str:
    if confidence < 40:
        return "NEUTRAL (Collecting Data)"
    diff = predicted - current
    if diff > 1200:
        return "BUY NOW 🔥 (Price Rising)"
    if diff < -1200:
        return "WAIT ⏳ (Likely to Drop)"
    return "FAIR PRICE ✅"


# ══════════════════════════════════════════════════════════════════════
# GET /ai/price
# ══════════════════════════════════════════════════════════════════════

@router.get("/price", tags=["AI"])
async def predict_price_get(
    origin: str,
    destination: str,
    departure_date: str,
):
    """
    GET-based price prediction for widgets and dashboards.
    Matches the locked 2026 XGBoost feature set.
    """
    try:
        predictor = get_predictor()
        origin = origin.upper().strip()
        destination = destination.upper().strip()

        if origin == destination:
            raise HTTPException(400, detail="Origin and destination must differ")

        try:
            dep_date_obj = datetime.strptime(departure_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, detail="Invalid date — use YYYY-MM-DD")

        # ── Route context ──────────────────────────────────────────────
        route = (
            db.supabase.table("routes")
            .select("*")
            .eq("origin_code", origin)
            .eq("destination_code", destination)
            .limit(1)
            .execute()
        )
        if not route.data:
            raise HTTPException(404, detail="Route not currently supported.")

        route_data = route.data[0]

        # ── Build features ────────────────────────────────────────────
        now_ist = datetime.now(IST)
        today_ist = now_ist.date()
        days_until_dep = max((dep_date_obj - today_ist).days, 0)
        hour = now_ist.hour

        # Calculate Price Changes for Features
        recent_prices = _get_recent_prices(origin, destination)
        p0 = recent_prices[0] if len(recent_prices) >= 1 else 0.0
        p1 = recent_prices[1] if len(recent_prices) >= 2 else p0
        p3 = recent_prices[3] if len(recent_prices) >= 4 else p1

        airlines = route_data.get("airlines") or ["AI"]
        primary_airline = airlines[0] if isinstance(airlines, list) and airlines else "AI"

        # 🎯 MATCHING FEATURE SET (MUST MATCH PRICEPREDICTOR.FEATURE_COLS)
        features = {
            "origin_code": origin,
            "destination_code": destination,
            "airline_code": primary_airline,
            "days_until_dep": float(days_until_dep),
            "urgency": 1 / (days_until_dep + 1), # Pre-calculated for model
            "day_of_week": dep_date_obj.weekday(),
            "month": dep_date_obj.month,
            "week_of_year": dep_date_obj.isocalendar()[1],
            "hour_of_day": hour,
            "is_peak_hour": 1 if hour in [7, 8, 9, 18, 19, 20, 21] else 0,
            "is_live": True, # Crucial for 2026 priority logic
            "seats_available": 30, # Base assumption for widget queries
            "price_change_1d": float(p0 - p1),
            "price_change_3d": float(p0 - p3),
            "demand_score": 0.85 if days_until_dep < 7 else 0.5,
            "seasonality_factor": 1.25 if dep_date_obj.month in [4, 5, 10, 12] else 1.0,
        }

        # ── Prediction & Market Blending ──────────────────────────────
        model_price = predictor.predict(features)
        market_median = _get_market_median(recent_prices)

        # Market-Aware Smoothing
        if market_median:
            # We trust the live market median more if we have many recent data points
            live_weight = min(len(recent_prices) / 10, 0.60) 
            final_price = (model_price * (1 - live_weight)) + (market_median * live_weight)
        else:
            final_price = model_price

        final_price = _adjust_prediction(final_price)

        # ── Intelligence Output ───────────────────────────────────────
        volatility = float(np.std(recent_prices)) if len(recent_prices) > 1 else 800.0
        confidence = _calculate_confidence(len(recent_prices), volatility)
        
        # Reference point for recommendation
        current_ref = p0 if p0 > 0 else (market_median if market_median else final_price * 0.95)

        return {
            "status": "success",
            "data": {
                "origin": origin,
                "destination": destination,
                "predicted_price": final_price,
                "intelligence": {
                    "confidence": f"{confidence}%",
                    "recommendation": _get_smart_recommendation(current_ref, final_price, confidence),
                    "market_status": "VOLATILE" if volatility > 1200 else "STABLE",
                    "days_to_go": days_until_dep,
                },
                "meta": {
                    "peak_season": features["seasonality_factor"] > 1.1,
                    "weekend": dep_date_obj.weekday() >= 5,
                    "timestamp": datetime.now(IST).isoformat(),
                },
            },
        }

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Intelligence Engine error.")