"""Test Suite for Recommendation Validation Service."""

import pytest
from backend.services.recommendation_validation import recommendation_validation_service

def test_recommendation_validation_consistent():
    rec = {"decision": "BUY"}
    res = recommendation_validation_service.validate_recommendation(
        recommendation=rec,
        current_lowest_fare=5000.0,
        predicted_price=5800.0  # +16% expected increase
    )
    assert res["valid"] is True
    assert len(res["errors"]) == 0

def test_recommendation_validation_contradiction():
    rec = {"decision": "BUY"}
    res = recommendation_validation_service.validate_recommendation(
        recommendation=rec,
        current_lowest_fare=5000.0,
        predicted_price=4000.0  # -20% expected drop
    )
    assert res["valid"] is False
    assert len(res["errors"]) > 0
