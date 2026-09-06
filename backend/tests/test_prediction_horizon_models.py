import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.ml.price_model import PricePredictor

def test_prediction_horizon_models_supported():
    """Verify independent models are registered and maintained for each horizon."""
    predictor = PricePredictor()
    assert predictor.supported_horizons == [1, 3, 7]
    # Horizon 0 is not a trainable target; see MIN_TRAINABLE_HORIZON_DAYS.
    assert 0 not in predictor.supported_horizons

    # Mock trained state
    mock_model_1 = MagicMock()
    mock_model_1.predict.return_value = [5500.0]
    mock_model_3 = MagicMock()
    mock_model_3.predict.return_value = [6000.0]
    mock_model_7 = MagicMock()
    mock_model_7.predict.return_value = [6200.0]

    predictor.models = {
        1: mock_model_1,
        3: mock_model_3,
        7: mock_model_7,
    }
    predictor.legacy_mode = False
    predictor._trained = True

    # Predict should invoke matching model for specific horizon
    mock_features = {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E", "days_until_dep": 5}

    predictor.predict(mock_features, horizon=1)
    assert mock_model_1.predict.called
    assert not mock_model_3.predict.called

    predictor.predict(mock_features, horizon=3)
    assert mock_model_3.predict.called
