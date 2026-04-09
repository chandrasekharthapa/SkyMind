"""
SkyMind — AI Price Prediction Router  (/ai/price)
Refined for 2026 Production UI

FIX: predict_price_get now generates a 30-day forecast array so that
     POST /predict (which delegates here) returns real forecast data
     instead of always falling back to the synthetic frontend generator.
"""

import os
import traceback
from datetime import datetime, timedelta

import numpy as np
import pytz

from fastapi import APIRouter, HTTPException, Request
from ml.price_model import get_predictor
from database.database import database as db
from services.amadeus import amadeus_service

router = APIRouter()

IST = pytz.timezone("Asia/Kolkata")


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _adjust_prediction(price: float) -> float:
    return round(max(2800.0, min(45_000.0, price)), 2)


def _get_recent_prices(origin: str, destination: str) -> list[float]:
    try:
        res = (
            db.supabase.table("price_history")
            .select("price")
            .eq("origin_code", origin)
            .eq("destination_code", destination)
            .order("recorded_at", desc=True)
            .limit(30)
            .execute()
        )
        return [float(r["price"]) for r in (res.data or [])]
    except Exception:
        return []


def _get_market_median(prices: list[float]) -> float | None:
    if not prices:
        return None
    return float(np.median(prices))


def _calculate_confidence(
    recent_count: int, volatility: float, is_live_boost: bool = False
) -> float:
    base = min(recent_count / 15, 1) * 65
    stability = max(0.0, 30 - (volatility / 1500))
    live_bonus = 5.0 if is_live_boost else 0.0
    return round(max(20.0, min(90.0, base + stability + live_bonus)), 2)


def _generate_forecast(
    base_price: float,
    trend: str,
    volatility: float,
    start_date: datetime,
    days: int = 30,
) -> list[dict]:
    """
    Generate a deterministic 30-day price forecast with confidence intervals.
    Uses a linear trend + weekly seasonality component.
    """
    slope_map = {"RISING": 0.007, "FALLING": -0.005, "STABLE": 0.001}
    slope = slope_map.get(trend, 0.001) * base_price
    std = max(volatility * 0.4, base_price * 0.03)

    forecast = []
    for i in range(days):
        day_date = start_date + timedelta(days=i + 1)
        trend_component = slope * i
        seasonality = base_price * 0.025 * np.sin(2 * np.pi * (i + 3) / 7)
        price = max(800.0, base_price + trend_component + seasonality)
        forecast.append(
            {
                "day": i + 1,
                "date": day_date.strftime("%Y-%m-%d"),
                "price": round(price, 2),
                "lower": round(max(800.0, price - std), 2),
                "upper": round(price + std, 2),
            }
        )
    return forecast


# ══════════════════════════════════════════════════════════════════════
# GET /ai/price  (also called by POST /predict in main.py)
# ══════════════════════════════════════════════════════════════════════

@router.get("/price", tags=["AI"])
async def predict_price_get(
    origin: str,
    destination: str,
    departure_date: str,
):
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

        now_ist = datetime.now(IST)
        today_ist = now_ist.date()
        days_until_dep = max((dep_date_obj - today_ist).days, 0)
        hour = now_ist.hour

        # ── RECENT PRICE SIGNALS ─────────────────────────
        recent_prices = _get_recent_prices(origin, destination)
        p0 = recent_prices[0] if len(recent_prices) >= 1 else 0.0
        p1 = recent_prices[1] if len(recent_prices) >= 2 else p0
        p3 = recent_prices[3] if len(recent_prices) >= 4 else p1

        airlines = route_data.get("airlines") or ["AI"]
        primary_airline = (
            airlines[0] if isinstance(airlines, list) and airlines else "AI"
        )

        # ── MODEL FEATURES ───────────────────────────────
        features = {
            "origin_code": origin,
            "destination_code": destination,
            "airline_code": primary_airline,
            "days_until_dep": float(days_until_dep),
            "urgency": 1 / (days_until_dep + 1),
            "day_of_week": dep_date_obj.weekday(),
            "month": dep_date_obj.month,
            "week_of_year": dep_date_obj.isocalendar()[1],
            "hour_of_day": hour,
            "is_peak_hour": 1 if hour in [7, 8, 9, 18, 19, 20, 21] else 0,
            "is_live": 1.0,
            "seats_available": 50,
            "price_change_1d": float(p0 - p1),
            "price_change_3d": float(p0 - p3),
            "demand_score": 0.85 if days_until_dep < 7 else 0.5,
            "seasonality_factor": (
                1.25 if dep_date_obj.month in [4, 5, 10, 12] else 1.0
            ),
        }

        # ── MODEL PREDICTION ─────────────────────────────
        model_price = predictor.predict(features)
        market_median = _get_market_median(recent_prices)

        if market_median:
            live_weight = min(len(recent_prices) / 10, 0.75)
            final_price = (model_price * (1 - live_weight)) + (
                market_median * live_weight
            )
        else:
            final_price = model_price

        final_price = _adjust_prediction(final_price)

        # ── CONFIDENCE ───────────────────────────────────
        volatility = (
            float(np.std(recent_prices)) if len(recent_prices) > 1 else 800.0
        )
        confidence = _calculate_confidence(
            len(recent_prices), volatility, is_live_boost=True
        )

        # ── CURRENT PRICE ────────────────────────────────
        
        filtered_prices = [p for p in recent_prices if 3000 < p < 8000]
        if filtered_prices:
            current_ref = min(filtered_prices)
        elif recent_prices:
            current_ref = min(recent_prices)
        else:
            current_ref = final_price * 0.95

        # ── TREND / PROBABILITY ──────────────────────────
        diff = final_price - current_ref
        scale = max(volatility, 500)
        prob_increase = 1 / (1 + np.exp(-diff / scale))
        prob_increase = float(np.clip(prob_increase, 0.05, 0.95))

        change_pct = ((final_price - current_ref) / max(current_ref, 1)) * 100

        if len(recent_prices) >= 5:
            trend_diff = recent_prices[0] - recent_prices[-1]
            if trend_diff > 300:
                trend = "RISING"
            elif trend_diff < -300:
                trend = "FALLING"
            else:
                trend = "STABLE"
        else:
                trend = "STABLE"
        threshold = max(volatility * 0.3, current_ref * 0.08)

        if diff > threshold:
            recommendation = "BUY_NOW"
        elif diff < -threshold:
            recommendation = "WAIT"
        else:
            recommendation = "HOLD"

        # ── FORECAST (FIX: now generated server-side) ────
        forecast = _generate_forecast(
            base_price=final_price,
            trend=trend,
            volatility=volatility,
            start_date=now_ist.replace(tzinfo=None),
            days=30,
        )

        # ── RESPONSE ─────────────────────────────────────
        return {
            "status": "success",
            "data": {
                "origin": origin,
                "destination": destination,
                "live_price": current_ref,
                "predicted_price": final_price,
                "trend": trend,
                "change_percent": round(change_pct, 2),
                "forecast": forecast,
                "intelligence": {
                    "confidence": confidence,
                    "prob_increase": round(prob_increase, 2),
                    "recommendation": recommendation,
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


# ══════════════════════════════════════════════════════════════════════
# POST /ai/train-dedicated-2026
# ══════════════════════════════════════════════════════════════════════

@router.post("/train-dedicated-2026", tags=["AI Automation"])
async def trigger_training(request: Request):
    auth_header = request.headers.get("Authorization")
    secret_key = os.getenv("CRON_SECRET")

    if not auth_header or auth_header != f"Bearer {secret_key}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        predictor = get_predictor()
        predictor.train()
        return {"status": "success", "message": "Model retrained"}
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Retrain failed")