import pytest
from backend.services.model_schema_validator import ModelSchemaValidator

def test_prediction_schema_validator_fails_fast():
    """Verify schema validator fails fast on order/count feature mismatch."""
    expected = ["origin_code", "destination_code", "airline_code"]
    
    # 1. Mismatch count
    features_count_mismatch = {"origin_code": 1, "destination_code": 2}
    with pytest.raises(ValueError, match="Feature count mismatch"):
        ModelSchemaValidator.validate_schema(features_count_mismatch, expected)
        
    # 2. Mismatch order
    features_order_mismatch = {"destination_code": 2, "origin_code": 1, "airline_code": 3}
    with pytest.raises(ValueError, match="Feature schema mismatch"):
        ModelSchemaValidator.validate_schema(features_order_mismatch, expected)
