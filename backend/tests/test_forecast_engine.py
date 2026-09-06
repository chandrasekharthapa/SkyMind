import pytest
from unittest.mock import MagicMock
from backend.services.forecast_engine import ForecastEngine
from backend.utils.exceptions import PredictionUnavailable

def test_forecast_engine_only_via_trained_models():
    """Verify ForecastEngine only produces forecasts via trained models, raising error otherwise."""
    mock_registry = MagicMock()
    mock_registry.supports_forecasting = False  # Not trained/supported
    
    engine = ForecastEngine(model_registry=mock_registry)
    
    snapshot_ctx = {"origin": "DEL", "destination": "BOM"}
    features = {}
    
    with pytest.raises(PredictionUnavailable, match="Active model does not support forecasting"):
        engine.run_forecast(snapshot_ctx, features)
