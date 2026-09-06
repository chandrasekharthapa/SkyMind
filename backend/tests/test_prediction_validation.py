"""Test Suite for Prediction Validation."""

import pytest
from backend.services.prediction_validation import prediction_validation_service

def test_prediction_validation_service_valid():
    payload = {
        "predicted_price": 6000.0,
        "forecast": [
            {"day": 0, "price": 6000.0, "lower": 5500.0, "upper": 6500.0},
            {"day": 1, "price": 6300.0, "lower": 5800.0, "upper": 6800.0}
        ],
        "recommendation": {"decision": "MONITOR"}
    }
    res = prediction_validation_service.validate_prediction_response(payload)
    assert res["valid"] is True
    assert len(res["errors"]) == 0

def test_prediction_validation_service_invalid_price():
    payload = {
        "predicted_price": -500.0,
        "forecast": [],
        "recommendation": {"decision": "INVALID"}
    }
    res = prediction_validation_service.validate_prediction_response(payload)
    assert res["valid"] is False
    assert len(res["errors"]) > 0
