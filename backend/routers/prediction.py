"""
AI Price Prediction endpoints — REAL VERSION
Uses market-calibrated model with live Amadeus price anchoring.
"""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, date, timedelta

router = APIRouter()


@router.get("/price")
async def predict_price(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    departure_date: str = Query(..., description="YYYY-MM-DD"),
    live_price: float = Query(None, description="Current real price from flight search"),
):
    """
    Predict optimal booking time for a specific route + date.
    If live_price is provided (from Amadeus search), anchors the model to it.
    """
    try:
        from ml.price_predictor import predictor
        dep_date_obj = datetime.strptime(departure_date, "%Y-%m-%d").date()
        days_until = (dep_date_obj - date.today()).days
        
        if days_until < 0:
            raise HTTPException(400, "Departure date must be in the future")
        
        result = predictor.forecast_with_analysis(
            origin=origin.upper(),
            destination=destination.upper(),
            departure_date=departure_date,
            live_anchor=live_price,
        )
        return {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_date": departure_date,
            "days_until_departure": days_until,
            **result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/forecast")
async def price_forecast(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    departure_date: str = Query(None, description="YYYY-MM-DD, defaults to 45 days out"),
    live_price: float = Query(None, description="Anchor to this real price"),
):
    """
    30-day booking price forecast. Shows how price changes as you wait to book.
    Each point = 'what would I pay if I booked on this date?'
    """
    try:
        from ml.price_predictor import predictor
        result = predictor.forecast_with_analysis(
            origin=origin.upper(),
            destination=destination.upper(),
            departure_date=departure_date,
            live_anchor=live_price,
        )
        forecast = result["forecast"]
        return {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_date": departure_date,
            "forecast": forecast,
            "best_day": result.get("best_day"),
            "worst_day": result.get("worst_day"),
            "trend": result["trend"],
            "recommendation": result["recommendation"],
            "data_quality": result.get("data_quality", "MODEL"),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/hidden-routes")
async def find_hidden_routes(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    departure_date: str = Query(...),
    direct_price: float = Query(..., description="Current direct flight price"),
):
    """Find cheaper hidden multi-stop routes using Dijkstra algorithm."""
    from ml.price_predictor import (
        get_baseline, advance_booking_multiplier,
        SEASONAL_MULTIPLIERS, DOW_MULTIPLIERS, is_international_route
    )
    from datetime import datetime as dt
    
    try:
        dep_date = dt.strptime(departure_date, "%Y-%m-%d").date()
    except Exception:
        dep_date = date.today() + timedelta(days=30)
    
    days_until = max((dep_date - date.today()).days, 1)
    
    # Hub airports to route through
    HUBS = {
        "DXB": "Dubai", "IST": "Istanbul", "DOH": "Doha",
        "SIN": "Singapore", "BOM": "Mumbai", "DEL": "Delhi",
        "BLR": "Bengaluru", "CCU": "Kolkata",
    }
    
    via_options = []
    
    for hub, hub_city in HUBS.items():
        if hub in (origin, destination):
            continue
        
        try:
            from ml.price_predictor import predict_price
            # Price of leg 1: origin → hub
            leg1 = predict_price(origin, hub, days_until, dep_date)
            # Price of leg 2: hub → destination (bought same day, slightly later)
            leg2 = predict_price(hub, destination, days_until, dep_date)
            total = leg1 + leg2
            
            # Only show if genuinely cheaper (account for connection time value)
            if total < direct_price * 0.88:  # at least 12% savings to be worth it
                savings = direct_price - total
                via_options.append({
                    "path": [origin, hub, destination],
                    "via_city": hub_city,
                    "total_price": round(total),
                    "leg1_price": round(leg1),
                    "leg2_price": round(leg2),
                    "stops": 1,
                    "savings_vs_direct": round(savings),
                    "savings_percent": round(savings / direct_price * 100, 1),
                })
        except Exception:
            pass
    
    via_options.sort(key=lambda x: x["total_price"])
    
    return {
        "origin": origin,
        "destination": destination,
        "direct_price": direct_price,
        "hidden_routes": via_options[:4],
        "message": f"Found {len(via_options)} cheaper alternatives" if via_options else "No cheaper routes found today",
    }
