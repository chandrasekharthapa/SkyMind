import pytest
import sys
import os
import numpy as np
from unittest.mock import AsyncMock, MagicMock

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.flight_search_service import flight_search_service
from backend.services.flight_data_service import flight_data_service, STATUS_OK
from backend.ml.price_model import get_predictor
from backend.tests.model_availability import requires_trained_model

@pytest.mark.asyncio
async def test_zero_synthetic_features_pipeline(monkeypatch):
    """Verify prediction pipeline passes np.nan and parsed values instead of synthetic defaults.

    Gated on a servable artifact, for the same reason as
    `test_prediction_zero_synthetic.py`: with no model on disk the predictor now
    refuses before a feature vector is ever built, so `captured_features` would be
    empty for a reason that has nothing to do with synthetic values. This test is the
    search-path counterpart of that one — it enters through
    `flight_search_service.search` rather than `prediction_service.predict` — so both
    are kept and both are gated.
    """
    requires_trained_model()

    # Mock MCP search return with missing seats and departure_time set.
    #
    # `status` is not decoration. The search service refuses a transport result that
    # carries no status — a transport that answers without one is treated as broken
    # rather than as an empty market — so a mock shaped like the old bare
    # `{"data": [...]}` sends this test down the DB-cache fallback, where `predict`
    # is never called and the assertions below never run against a live payload.
    # Mirror `flight_data_service._result` here; do not trim the envelope.
    mock_mcp_flights = {
        "data": [
            {
                "price": 9300.0,
                "currency": "INR",
                "primary_airline": "6E",
                "legs": [
                    {
                        "flight_number": "6261",
                        "airline_code": "6E",
                        "departure_time": "2026-07-26T08:30:00",
                        "arrival_time": "2026-07-26T10:45:00",
                        "duration": 135
                    }
                ]
            }
        ],
        "status": STATUS_OK,
        "error": None,
        "error_kind": None,
        "attempts": 1,
    }
    monkeypatch.setattr(flight_data_service, "search_flights", AsyncMock(return_value=mock_mcp_flights))
    
    # Mock Repository query to return empty database records
    monkeypatch.setattr(flight_search_service.repository, "get_price_history_cache", MagicMock(return_value=[]))
    monkeypatch.setattr(flight_search_service.repository, "search_airports", MagicMock(return_value=[]))

    # Spy on model.predict to capture passed features
    captured_features = []
    original_predict = get_predictor().predict
    
    def mock_predict(features):
        captured_features.append(features)
        # return a dummy prediction price
        return 9200.0
        
    monkeypatch.setattr(get_predictor(), "predict", mock_predict)

    # Trigger search
    presentation = await flight_search_service.search(
        origin_iata="DEL",
        destination_iata="BOM",
        departure_date="2026-07-26",
        adults=1,
        cabin_class="ECONOMY",
        sorting="price"
    )

    # Verify that predict was called
    assert len(captured_features) == 1
    features = captured_features[0]

    # Verify no synthetic defaults are used:
    # 1. Seats available must be np.nan because it was not provided in the MCP mock
    assert np.isnan(features["seats_available"])

    # 2. Heuristic demand score must be np.nan
    assert np.isnan(features["demand_score"])

    # 3. Manually assigned seasonality factor must be np.nan
    assert np.isnan(features["seasonality_factor"])

    # 4. Hour of day and peak hour must be derived from the departure time (08:30:00 -> hour 8)
    assert features["hour_of_day"] == 8.0
    assert features["is_peak_hour"] == 1.0  # 8 is peak hour (7-10 AM)

    # 5. Price changes must be np.nan because there was no database cache records to calculate averages from
    assert np.isnan(features["price_change_1d"])
    assert np.isnan(features["price_change_3d"])
