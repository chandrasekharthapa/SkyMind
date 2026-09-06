import pytest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.model_schema_validator import ModelSchemaValidator

def test_schema_validator_success():
    """Verify validation passes when schemas match exactly."""
    features = {"f1": 1, "f2": 2}
    expected = ["f1", "f2"]
    # Should complete without error
    ModelSchemaValidator.validate_schema(features, expected)

def test_schema_validator_count_mismatch():
    """Verify schema validator raises ValueError on count mismatch."""
    features = {"f1": 1}
    expected = ["f1", "f2"]
    with pytest.raises(ValueError, match="Feature count mismatch"):
        ModelSchemaValidator.validate_schema(features, expected)

def test_schema_validator_order_mismatch():
    """Verify schema validator raises ValueError on ordering mismatch."""
    features = {"f2": 2, "f1": 1}
    expected = ["f1", "f2"]
    with pytest.raises(ValueError, match="Feature schema mismatch at index 0"):
        ModelSchemaValidator.validate_schema(features, expected)
