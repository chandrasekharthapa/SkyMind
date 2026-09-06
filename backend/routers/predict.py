"""SkyMind — Price Prediction Router.

Thinned router validating inputs, executing prediction service pipeline,
and returning clean Pydantic v2 presentation schemas.
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from pydantic import BaseModel, field_validator
from datetime import datetime

from backend.services.prediction_service import prediction_service
from backend.services.prediction_presentation import PredictionResponse
from backend.ml.price_model import get_predictor

router = APIRouter()

class PredictRequest(BaseModel):
    origin: str
    destination: str
    departure_date: str
    airline_code: Optional[str] = None

    @field_validator("origin", "destination")
    @classmethod
    def normalize_airport(cls, value: str) -> str:
        airport = value.strip().upper()
        if len(airport) != 3 or not airport.isalpha():
            raise ValueError("Airport codes must be three-letter IATA codes.")
        return airport

    @field_validator("departure_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Departure date must match YYYY-MM-DD format.")
        return value

    @field_validator("airline_code")
    @classmethod
    def normalize_airline(cls, value: Optional[str]) -> Optional[str]:
        if value:
            val_clean = value.strip().upper()
            if len(val_clean) < 2 or len(val_clean) > 3 or not val_clean.isalnum():
                raise ValueError("Airline code must be 2-3 alphanumeric characters.")
            return val_clean
        return value


from backend.utils.exceptions import PredictionUnavailable

@router.post("/predict", response_model=PredictionResponse, tags=["Prediction"])
async def predict(req: PredictRequest):
    # Verify core ML predictor readiness.
    #
    # The detail string is rendered verbatim to the end user by the forecast page,
    # so it says what is true in words a traveller can read. It used to say "ML
    # model estimator is uninitialized or missing" — scikit-learn vocabulary for a
    # state that has nothing to do with initialisation: no artifact has ever
    # cleared the acceptance gate in `backend/ml/price_model.py`, which is a fact
    # about the training corpus, not a fault in this process. `_trained` is only
    # set by `train()` after that gate passes and by `load()` after the leak audit
    # passes, so its being False is the honest signal that there is nothing to
    # predict with.
    try:
        predictor = get_predictor()
        if not predictor or not getattr(predictor, "_trained", False):
            raise PredictionUnavailable(
                "No forecast model has been trained yet, so SkyMind will not "
                "guess where this fare is going. Fare search still works."
            )
    except Exception as e:
        if isinstance(e, PredictionUnavailable):
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=503, detail=f"Prediction engine initialization failure: {e}")

    try:
        response_data = await prediction_service.predict(
            origin=req.origin,
            destination=req.destination,
            departure_date=req.departure_date,
            airline_code=req.airline_code
        )
        return response_data
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except PredictionUnavailable as un_err:
        raise HTTPException(status_code=503, detail=str(un_err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prediction pipeline inference error: {exc}")
