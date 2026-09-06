from datetime import datetime, timezone
import pandas as pd
from backend.ml.feature_context import FeatureContext

def test_feature_context_immutability():
    ctx = FeatureContext(
        historical_data=[],
        market_snapshot={},
        prediction_context={},
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime.now(timezone.utc)
    )
    
    # Assert that mutating attributes is disabled (frozen dataclass)
    import pytest
    with pytest.raises(AttributeError):
        ctx.route_statistics = {"something": "else"}
