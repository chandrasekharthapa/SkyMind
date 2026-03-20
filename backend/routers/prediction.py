"""
AI Price Prediction endpoints.
"""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, date
from ml.price_model import get_predictor, HiddenRouteFinder
from services.amadeus import amadeus_service, parse_flight_offers

router = APIRouter()


@router.get("/price")
async def predict_price(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    departure_date: str = Query(..., description="YYYY-MM-DD"),
    airline_code: str = Query("AI"),
):
    """Predict optimal booking time and expected price."""
    predictor = get_predictor()
    dep_date = datetime.strptime(departure_date, "%Y-%m-%d")
    days_until = (dep_date.date() - date.today()).days

    if days_until < 0:
        raise HTTPException(status_code=400, detail="Departure date must be in the future")

    result = predictor.predict(
        days_until_departure=days_until,
        departure_date=dep_date,
        airline_code=airline_code,
        origin_code=origin,
        destination_code=destination,
    )
    return {
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "days_until_departure": days_until,
        **result,
    }


@router.get("/forecast")
async def price_forecast(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    base_price: float = Query(8000.0, description="Current base price for context"),
):
    """Get 30-day price forecast for a route."""
    predictor = get_predictor()
    forecast = predictor.forecast_30_days(origin, destination, base_price)
    return {
        "origin": origin,
        "destination": destination,
        "forecast": forecast,
        "best_day": min(forecast, key=lambda x: x["price"]),
        "worst_day": max(forecast, key=lambda x: x["price"]),
    }


@router.get("/hidden-routes")
async def find_hidden_routes(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    departure_date: str = Query(...),
    direct_price: float = Query(..., description="Current direct flight price"),
):
    """Find cheaper hidden multi-stop routes using Dijkstra algorithm."""
    # Common hub prices (in reality, we'd query Amadeus for each pair)
    ROUTE_PRICES = {
        ("DEL", "DXB"): 4500, ("DXB", "LHR"): 12000, ("DXB", "CDG"): 11000,
        ("DEL", "IST"): 15000, ("IST", "CDG"): 8000, ("IST", "LHR"): 9000,
        ("DEL", "SIN"): 8000, ("SIN", "SYD"): 12000, ("SIN", "NRT"): 14000,
        ("BOM", "DXB"): 4000, ("BOM", "SIN"): 7500, ("DEL", "BKK"): 7000,
        ("BKK", "NRT"): 11000, ("DEL", "CDG"): 38000, ("DEL", "LHR"): 35000,
    }

    finder = HiddenRouteFinder()

    # Build graph
    for (o, d), price in ROUTE_PRICES.items():
        finder.add_route(o, d, price)
        finder.add_route(d, o, price)  # Bidirectional

    hidden = finder.find_hidden_routes(origin, destination, direct_price)

    # Also try to query Amadeus for via-hub prices
    via_options = []
    hubs = ["DXB", "IST", "SIN", "DOH"]
    for hub in hubs:
        if hub == origin or hub == destination:
            continue
        # Check if we have data for these legs
        leg1_key = (origin, hub)
        leg2_key = (hub, destination)
        if leg1_key in ROUTE_PRICES and leg2_key in ROUTE_PRICES:
            total = ROUTE_PRICES[leg1_key] + ROUTE_PRICES[leg2_key]
            if total < direct_price:
                via_options.append({
                    "path": [origin, hub, destination],
                    "total_price": total,
                    "stops": 1,
                    "via": hub,
                    "savings_vs_direct": round(direct_price - total, 2),
                    "savings_percent": round((direct_price - total) / direct_price * 100, 1),
                })

    return {
        "origin": origin,
        "destination": destination,
        "direct_price": direct_price,
        "hidden_routes": via_options[:5],
        "message": f"Found {len(via_options)} cheaper alternatives to direct flight",
    }
