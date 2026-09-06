import pytest
from unittest.mock import MagicMock
from backend.services.model_registry import ModelRegistry

def test_model_registry_capabilities_discovery():
    """Verify ModelRegistry discovers model capabilities, version, target."""
    mock_predictor = MagicMock()
    mock_predictor.model_version = "2.5.0"
    mock_predictor.feature_schema_version = "2.5.0"
    # The real predictor's own wording, so this fixture does not keep the retired
    # "Future Lowest Fare" description alive in the test suite.
    mock_predictor.training_target = (
        "Fare on the same booking curve at the earliest observation on or "
        "after t + horizon days, within tolerance"
    )
    mock_predictor.supported_horizons = [1, 3, 7]
    mock_predictor.supports_forecasting = True
    # Set explicitly because `supports_forecasting` reads all three: a MagicMock's
    # auto-generated `legacy_mode` is truthy, which short-circuits the property and
    # made the assertion below pass without ever consulting `models`. The branch
    # under test is the non-legacy one, where a loaded horizon model is required.
    mock_predictor.legacy_mode = False
    mock_predictor.models = {1: object()}

    registry = ModelRegistry(predictor=mock_predictor)

    assert registry.model_version == "2.5.0"
    assert registry.feature_schema_version == "2.5.0"
    assert registry.target_definition == mock_predictor.training_target
    assert registry.training_target == registry.target_definition
    assert registry.supported_horizons == [1, 3, 7]
    assert registry.supports_forecasting is True
