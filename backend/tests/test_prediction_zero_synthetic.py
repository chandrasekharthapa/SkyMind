import pytest
import sys
import os
import numpy as np
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.prediction_service import prediction_service
from backend.services.flight_search_service import flight_search_service
from backend.ml.price_model import get_predictor
from backend.tests.model_availability import requires_trained_model

# Dynamic future date so this test never fails due to date drift
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")

@pytest.mark.asyncio
async def test_prediction_zero_synthetic_regression(monkeypatch):
    """Verify that every feature sent to the model is derived, provider-sourced, or null.

    Gated on a servable artifact: the assertion inspects the feature dict that
    reaches the predictor, and with no model loaded `predict` refuses before any
    feature is built, so `captured_features` is empty for a reason that has nothing
    to do with synthetic values. Note what the gate costs — this is the only test
    that inspects the *live* feature dict, so while it is skipped the no-fabrication
    claim rests on the layers below it (`test_zero_synthetic_data.py` on the
    normalizer, `test_missing_values.py` and `test_feature_vector.py` on the builder),
    none of which sees the dict this one captures.
    """
    requires_trained_model()

    # Mock search flights returns empty data
    monkeypatch.setattr(flight_search_service, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(prediction_service.repository, "get_price_history_cache", MagicMock(return_value=[]))
    monkeypatch.setattr(prediction_service.repository, "search_airports", MagicMock(return_value=[]))

    captured_features = []
    
    def spy_predict(features, horizon=3):
        captured_features.append(features)
        return 9000.0

    monkeypatch.setattr(get_predictor(), "predict", spy_predict)

    # Invoke prediction service
    await prediction_service.predict(
        origin="DEL",
        destination="BOM",
        departure_date=FUTURE_DATE,
        airline_code=None
    )

    assert len(captured_features) == 5

    for features in captured_features:
        # Check seats_available
        seats = features.get("seats_available")
        assert seats not in [30, 50, 30.0, 50.0], f"Seats available has synthetic value: {seats}"

        # Check demand_score
        demand = features.get("demand_score")
        assert demand not in [0.5, 0.85], f"Demand score has synthetic value: {demand}"

        # Check seasonality_factor
        seasonality = features.get("seasonality_factor")
        assert seasonality not in [1.0, 1.2, 1.25], f"Seasonality factor has synthetic value: {seasonality}"

        # Check airline_code
        airline = features.get("airline_code")
        # Since no airline was requested and search returned empty, airline must be np.nan or None, not defaulted to 6E
        assert airline != "6E", "Airline code defaulted to 6E!"

        # Verify all features are either standard types or np.nan
        for key, val in features.items():
            is_valid = (
                val is None or
                isinstance(val, (int, float, bool, str, np.bool_)) or
                (isinstance(val, float) and np.isnan(val))
            )
            assert is_valid, f"Feature {key} has unverified value {val}!"
