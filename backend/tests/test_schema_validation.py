import pytest
from backend.services.model_schema_validator import ModelSchemaValidator

def test_schema_validator_fails_immediately():
    expected_cols = ["a", "b", "c"]
    
    # 1. Matches ordering and columns count
    ModelSchemaValidator.validate_schema({"a": 1, "b": 2, "c": 3}, expected_cols)
    
    # 2. Count mismatch raises ValueError
    with pytest.raises(ValueError):
         ModelSchemaValidator.validate_schema({"a": 1, "b": 2}, expected_cols)
         
    # 3. Order mismatch raises ValueError
    with pytest.raises(ValueError):
         ModelSchemaValidator.validate_schema({"b": 2, "a": 1, "c": 3}, expected_cols)
         
    # 4. Missing required feature raises ValueError
    with pytest.raises(ValueError):
         ModelSchemaValidator.validate_schema({"a": 1, "b": 2, "d": 4}, expected_cols)
