"""
SkyMind – FastAPI Backend (REAL ML VERSION)
============================================
Key improvements over previous version:
1. Uses real market-calibrated price model (not hash sine waves)
2. Fetches live Amadeus prices and uses them as anchors for predictions
3. Proper advance booking curve, seasonality, day-of-week factors
4. Meaningful recommendations based on actual price dynamics
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import traceback
import uuid
from datetime import datetime, date, timedelta
import asyncio
import logging

logger = logging.getLogger(__name__)

# Import real predictor (not the old hash-based one)
from ml.price_predictor import predictor

# ---------------------------------------------------------------------------
# City → IATA mapping
# ---------------------------------------------------------------------------
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
    "guwahati": "GAU",
    "varanasi": "VNS",
    "patna": "PAT",
    "bhubaneswar": "BBI",
    "ranchi": "IXR",
    "chandigarh": "IXC",
    "srinagar": "SXR",
    "jammu": "IXJ",
    "leh": "IXL",
    "dehradun": "DED",
    "imphal": "IMF",
    "nagpur": "NAG",
    "indore": "IDR",
    "bhopal": "BHO",
    "raipur": "RPR",
    "visakhapatnam": "VTZ", "vizag": "VTZ",
    "coimbatore": "CJB",
    "madurai": "IXM",
    "trichy": "TRZ", "tiruchirappalli": "TRZ",
    "trivandrum": "TRV", "thiruvananthapuram": "TRV",
    "kozhikode": "CCJ", "calicut": "CCJ",
    "mangalore": "IXE",
    "mysore": "MYQ", "mysuru": "MYQ",
    "siliguri": "IXB",
    "udaipur": "UDR",
    "jodhpur": "JDH",
    "port blair": "IXZ",
    "dubai": "DXB",
    "london": "LHR",
    "singapore": "SIN",
    "doha": "DOH",
    "abu dhabi": "AUH",
    "bangkok": "BKK",
    "kuala lumpur": "KUL",
    "new york": "JFK",
    "tokyo": "NRT",
    "istanbul": "IST",
}

AIRLINE_MAP = {
    "AI": "Air India", "6E": "IndiGo", "UK": "Vistara",
    "SG": "SpiceJet", "IX": "Air India Express", "QP": "Akasa Air",
    "EK": "Emirates", "SQ": "Singapore Airlines", "QR": "Qatar Airways",
    "EY": "Etihad Airways", "BA": "British Airways", "TK": "Turkish Airlines",
    "MH": "Malaysia Airlines", "FZ": "flydubai", "G9": "Air Arabia",
}

def resolve_iata(code: str) -> str:
    if not code:
        return code
    s = code.strip()
    lower = s.lower()
    if lower in CITY_TO_IATA:
        return CITY_TO_IATA[lower]
    return s.upper()

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SkyMind AI API",
    version="4.0.0",
    description="Real market-calibrated flight price prediction",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
try:
    from routers import flights, prediction, booking, payment, auth, notifications, alerts, user
    app.include_router(flights.router,       prefix="/flights",       tags=["flights"])
    app.include_router(prediction.router,    prefix="/prediction",    tags=["prediction"])
    app.include_router(booking.router,       prefix="/booking",       tags=["booking"])
    app.include_router(payment.router,       prefix="/payment",       tags=["payment"])
    app.include_router(auth.router,          prefix="/auth",          tags=["auth"])
    app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
    app.include_router(alerts.router,        prefix="/alerts",        tags=["alerts"])
    app.include_router(user.router,          prefix="/user",          tags=["user"])
except Exception as e:
    logger.warning(f"Could not mount some routers: {e}")

# In-memory alert store
_alerts: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Background task: fetch live Amadeus prices to anchor predictions
# ---------------------------------------------------------------------------
POPULAR_ROUTES = [
    ("DEL", "BOM"), ("DEL", "BLR"), ("DEL", "MAA"), ("DEL", "HYD"),
    ("DEL", "CCU"), ("BOM", "BLR"), ("BOM", "GOI"), ("BLR", "MAA"),
    ("DEL", "DXB"), ("BOM", "DXB"),
]

async def refresh_live_prices():
    """
    Periodically fetch live prices from Amadeus for popular routes.
    These anchor the prediction model to real market prices.
    """
    while True:
        await asyncio.sleep(1800)  # every 30 minutes
        try:
            import os
            if not os.getenv("AMADEUS_CLIENT_ID"):
                continue
            
            from services.amadeus import amadeus_service
            tomorrow = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
            
            for origin, destination in POPULAR_ROUTES[:5]:  # limit API calls
                try:
                    raw = await amadeus_service.search_flights(
                        origin=origin,
                        destination=destination,
                        departure_date=tomorrow,
                        adults=1,
                        max_results=5,
                    )
                    data = raw.get("data", [])
                    if data:
                        prices = [
                            float(o.get("price", {}).get("grandTotal", 0) or
                                  o.get("price", {}).get("total", 0))
                            for o in data
                        ]
                        prices = [p for p in prices if p > 0]
                        if prices:
                            live_price = float(min(prices))
                            predictor.cache_live_price(origin, destination, live_price)
                            logger.info(f"Live price {origin}→{destination}: ₹{live_price:,.0f}")
                    await asyncio.sleep(2)  # rate limit
                except Exception as e:
                    logger.debug(f"Live price fetch {origin}→{destination}: {e}")
        except Exception as e:
            logger.error(f"refresh_live_prices error: {e}")

async def check_alerts_background():
    """Check stored alerts against current prices every 30 min."""
    while True:
        await asyncio.sleep(1800)
        for alert_id, alert in list(_alerts.items()):
            try:
                result = predictor.forecast_with_analysis(
                    origin=alert["origin"],
                    destination=alert["destination"],
                    departure_date=alert.get("departure_date"),
                )
                current = result["predicted_price"]
                if current <= alert["target_price"] and not alert.get("triggered"):
                    alert["triggered"] = True
                    alert["triggered_at"] = datetime.utcnow().isoformat()
                    alert["current_price"] = current
                    logger.info(f"Alert triggered: {alert['origin']}→{alert['destination']} ₹{current:,.0f}")
            except Exception:
                pass

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(refresh_live_prices())
    asyncio.create_task(check_alerts_background())
    try:
        from services.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler not started: {e}")

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class PredictRequest(BaseModel):
    origin: str
    destination: str
    departure_date: str | None = None
    live_price: float | None = None  # optionally pass current price from search results

    @field_validator("origin", "destination")
    @classmethod
    def resolve(cls, v: str) -> str:
        return resolve_iata(v.strip())

class SetAlertRequest(BaseModel):
    origin: str
    destination: str
    target_price: float
    departure_date: str | None = None
    user_label: str | None = None
    user_id: str | None = None
    notify_email: str | None = None
    notify_phone: str | None = None

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "SkyMind AI API",
        "version": "4.0.0",
        "model": "market-calibrated",
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/")
def root():
    return {"status": "ok", "version": "4.0.0", "model": "market-calibrated"}

@app.post("/predict")
def predict(body: PredictRequest):
    """
    AI-driven flight price forecast.
    Uses real advance-booking curves, seasonality, and day-of-week factors.
    If live_price is passed (e.g. from current Amadeus search), it anchors
    the model to the real market price.
    """
    origin = resolve_iata(body.origin)
    destination = resolve_iata(body.destination)
    
    if origin == destination:
        raise HTTPException(422, "Origin and destination cannot be the same")
    
    # If caller passes a live price from their flight search, use it
    live_anchor = body.live_price
    if not live_anchor:
        # Check our cache
        live_anchor = predictor._get_cached_live_price(origin, destination)
    
    try:
        result = predictor.forecast_with_analysis(
            origin=origin,
            destination=destination,
            departure_date=body.departure_date,
            live_anchor=live_anchor,
        )
        return result
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, "Prediction failed — check server logs")

@app.get("/resolve-airport")
def resolve_airport(q: str):
    return {"input": q, "iata": resolve_iata(q)}

@app.post("/set-alert")
def set_alert(body: SetAlertRequest):
    origin = resolve_iata(body.origin)
    destination = resolve_iata(body.destination)
    
    if not origin or not destination or origin == destination:
        raise HTTPException(422, "Invalid origin/destination")
    if body.target_price <= 0:
        raise HTTPException(422, "Target price must be positive")
    
    alert_id = str(uuid.uuid4())[:8]
    _alerts[alert_id] = {
        "id": alert_id,
        "origin": origin,
        "destination": destination,
        "target_price": body.target_price,
        "departure_date": body.departure_date,
        "user_label": body.user_label or f"{origin}→{destination}",
        "user_id": body.user_id,
        "notify_email": body.notify_email,
        "notify_phone": body.notify_phone,
        "created_at": datetime.utcnow().isoformat(),
        "triggered": False,
        "current_price": None,
    }
    return {
        "success": True,
        "alert_id": alert_id,
        "message": f"Alert set for {origin}→{destination} at ₹{body.target_price:,.0f}",
    }

@app.get("/check-alerts")
def check_alerts(user_id: str | None = None):
    triggered = []
    all_alerts = []
    
    for alert_id, alert in _alerts.items():
        if user_id and alert.get("user_id") and alert["user_id"] != user_id:
            continue
        try:
            result = predictor.forecast_with_analysis(
                origin=alert["origin"],
                destination=alert["destination"],
                departure_date=alert.get("departure_date"),
            )
            current = result["predicted_price"]
            is_triggered = current <= alert["target_price"]
            
            enriched = {
                **alert,
                "current_price": current,
                "triggered": is_triggered,
                "savings": round(alert["target_price"] - current, 0) if is_triggered else 0,
                "trend": result["trend"],
                "recommendation": result["recommendation"],
            }
            all_alerts.append(enriched)
            if is_triggered:
                triggered.append(enriched)
        except Exception:
            all_alerts.append(alert)
    
    return {
        "alerts": all_alerts,
        "triggered": triggered,
        "triggered_count": len(triggered),
    }

@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str):
    if alert_id not in _alerts:
        raise HTTPException(404, "Alert not found")
    del _alerts[alert_id]
    return {"success": True}

@app.get("/airline-logo/{iata_code}")
def airline_logo(iata_code: str):
    code = iata_code.upper()
    return {
        "iata": code,
        "name": AIRLINE_MAP.get(code, code),
        "logo_url": f"https://content.airhex.com/content/logos/airlines_{code}_200_200_s.png",
    }

@app.get("/city-to-iata")
def city_to_iata_endpoint(city: str):
    return {"city": city, "iata": resolve_iata(city)}
