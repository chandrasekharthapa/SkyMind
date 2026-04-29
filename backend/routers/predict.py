"""Clean /predict route for SkyMind flight intelligence."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ml.price_model import get_predictor
from services.agents import make_decision
from services.flight_data_service import flight_data_service


router = APIRouter()


class PredictRequest(BaseModel):
    origin: str
    destination: str
    departure_date: str | None = None

    @field_validator("origin", "destination")
    @classmethod
    def normalize_airport(cls, value: str) -> str:
        airport = value.strip().upper()
        if len(airport) != 3:
            raise ValueError("Airport codes must be three-letter IATA codes.")
        return airport

    @field_validator("departure_date")
    @classmethod
    def validate_date(cls, value: str | None) -> str | None:
        if value:
            datetime.strptime(value, "%Y-%m-%d")
        return value


@router.post("/predict", tags=["Prediction"])
async def predict(req: PredictRequest) -> dict:
    if req.origin == req.destination:
        raise HTTPException(status_code=400, detail="Origin and destination must differ.")
    if not flight_data_service.route_supported(req.origin, req.destination):
        raise HTTPException(status_code=404, detail="Route is not currently supported.")

    snapshot = flight_data_service.market_snapshot(req.origin, req.destination, req.departure_date)
    predictor = get_predictor()

    features = {
        "origin_code": snapshot["origin"],
        "destination_code": snapshot["destination"],
        "airline_code": snapshot["airline"],
        "days_until_dep": snapshot["days_until_departure"],
        "day_of_week": datetime.strptime(snapshot["departure_date"], "%Y-%m-%d").weekday(),
        "month": int(snapshot["departure_date"][5:7]),
        "week_of_year": datetime.strptime(snapshot["departure_date"], "%Y-%m-%d").isocalendar().week,
        "seats_available": snapshot["seats_available"],
        "demand_score": snapshot["demand_score"],
        "seasonality_factor": snapshot["seasonality_factor"],
    }

    predicted_price = predictor.predict(features)
    forecast = predictor.forecast(snapshot, days=30)
    decision = make_decision({**snapshot, "current_price": predicted_price}, forecast)

    change_percent = 0.0
    trend = "STABLE"
    prob_increase = 0.5

    if len(forecast) >= 2:
        first = float(forecast[0]["price"])
        last = float(forecast[-1]["price"])
        if first > 0:
            change_percent = ((last - first) / first) * 100
            
        if change_percent > 3.0:
            trend = "RISING"
            prob_increase = 0.75 + min(0.2, change_percent / 100)
        elif change_percent < -3.0:
            trend = "FALLING"
            prob_increase = 0.25 - min(0.2, abs(change_percent) / 100)
        else:
            trend = "STABLE"
            prob_increase = 0.5 + (change_percent / 10)

    prob_increase = max(0.0, min(1.0, prob_increase))

    return {
        "predicted_price": predicted_price,
        "forecast": forecast,
        "decision": decision,
        "trend": trend,
        "change_percent": round(change_percent, 2),
        "intelligence": {
            "confidence": decision.get("confidence", 0.5) * 100,
            "prob_increase": round(prob_increase, 2),
            "recommendation": decision.get("decision", "MONITOR"),
            "market_status": "VOLATILE" if decision.get("confidence", 0.5) < 0.6 else "STABLE",
            "days_to_go": snapshot.get("days_until_departure", 0)
        }
    }


@router.get("/performance", tags=["Prediction"])
async def get_performance() -> dict:
    predictor = get_predictor()
    metrics = predictor.get_performance()
    return {"metrics": metrics}
