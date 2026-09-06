import pytest
from backend.services.recommendation_policy import RecommendationPolicy
from backend.services.recommendation_engine import RecommendationEngine

def test_recommendation_policy_dynamic_consumption():
    """Verify RecommendationEngine consumes policy thresholds dynamically."""
    policy = RecommendationPolicy(
        book_threshold_percent=2.0,
        wait_threshold_percent=-2.0,
        monitor_range_percent=2.0
    )
    
    engine = RecommendationEngine(recommendation_policy=policy)
    
    formatted_forecast = [
        {"day": 3, "price": 5200.0}
    ]
    
    # 1. 5200 is 4% higher than 5000. Under 2% book_threshold, this is BOOK_NOW
    #
    # The confidence arguments are passed explicitly even though this test is about
    # the decision, because omitting them used to produce a confidence of 95.0 from
    # the signature defaults. They are stated here as "measured" so the assertion
    # below is about the policy thresholds and nothing else.
    rec = engine.generate_recommendation(
        current_lowest=5000.0,
        formatted_forecast=formatted_forecast,
        prediction_horizon=3,
        predicted_price=5000.0,
        origin="DEL",
        destination="BOM",
        snapshot_quality=1.0,
        model_accuracy=90.59,
        is_live_market=True
    )
    assert rec["decision"] == "BOOK_NOW"
    assert rec["confidence"] == 90.59
    
    # 2. Under a custom business route rule (DEL-BOM business route threshold is 3%), 4% > 3% is BOOK_NOW
    # Let's verify route matching
    assert policy.get_thresholds("DEL", "BOM")["BOOK_THRESHOLD_PERCENT"] == 3.0
