import pytest
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.prediction_service import prediction_service
from backend.domain.market_snapshot import MarketSnapshot
from backend.tests.model_availability import requires_trained_model

client = TestClient(app)
FUTURE_DATE = (date.today() + timedelta(days=30)).isoformat()

@pytest.mark.asyncio
async def test_prediction_live_market_available():
    """Verify prediction succeeds when live market snapshot is available."""
    requires_trained_model()
    res = await prediction_service.predict(
        origin="DEL",
        destination="BOM",
        departure_date=FUTURE_DATE
    )
    assert res["predicted_price"] > 0
    assert res["search_metadata"]["provider_status"] in ["ONLINE", "DEGRADED"]
    assert "schema_version" in res

@pytest.mark.asyncio
async def test_prediction_live_market_unavailable_degraded_mode():
    """Verify prediction succeeds and enters DEGRADED mode when market snapshot is unavailable."""
    requires_trained_model()
    # Create empty market snapshot where lowest_fare is NaN
    empty_snapshot = MarketSnapshot(
        lowest_fare=float("nan"),
        highest_fare=float("nan"),
        average_fare=float("nan"),
        median_fare=float("nan"),
        fare_spread=float("nan"),
        price_std_dev=float("nan"),
        total_live_flights=0,
        direct_flight_count=0,
        connecting_flight_count=0,
        airline_distribution={},
        departure_distribution={"morning": 0, "afternoon": 0, "evening": 0},
        retrieval_timestamp="2026-07-21T18:00:00Z",
        provider="Offline Provider",
        search_duration=0.0,
        search_success=False,
        provider_status="DEGRADED"
    )

    with patch.object(
        prediction_service.market_snapshot_provider,
        "get_market_snapshot",
        new=AsyncMock(return_value=empty_snapshot)
    ):
        res = await prediction_service.predict(
            origin="DEL",
            destination="BOM",
            departure_date=FUTURE_DATE
        )
        
        # Verify prediction succeeded without throwing 503
        assert res["predicted_price"] > 0
        assert res["search_metadata"]["provider_status"] == "DEGRADED"
        assert res["search_metadata"]["prediction_mode"] == "historical_only"
        assert res["search_metadata"]["market_snapshot_available"] is False
        
        # Verify JSON serialization contains no NaN values
        raw_json = json.dumps(res)
        assert "NaN" not in raw_json
        assert "nan" not in raw_json

def test_prediction_http_endpoint_with_degraded_provider():
    """Test HTTP POST /api/v1/predict resolves cleanly when live market search is mocked out."""
    requires_trained_model()
    empty_snapshot = MarketSnapshot(
        lowest_fare=float("nan"),
        highest_fare=float("nan"),
        average_fare=float("nan"),
        median_fare=float("nan"),
        fare_spread=float("nan"),
        price_std_dev=float("nan"),
        total_live_flights=0,
        direct_flight_count=0,
        connecting_flight_count=0,
        airline_distribution={},
        departure_distribution={"morning": 0, "afternoon": 0, "evening": 0},
        retrieval_timestamp="2026-07-21T18:00:00Z",
        provider="Mock Provider",
        search_duration=0.0,
        search_success=False,
        provider_status="DEGRADED"
    )

    with patch.object(
        prediction_service.market_snapshot_provider,
        "get_market_snapshot",
        new=AsyncMock(return_value=empty_snapshot)
    ):
        response = client.post("/api/v1/predict", json={
            "origin": "DEL",
            "destination": "BOM",
            "departure_date": FUTURE_DATE
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["predicted_price"] > 0
        assert data["search_metadata"]["provider_status"] == "DEGRADED"
        assert data["search_metadata"]["market_snapshot_available"] is False

def test_prediction_model_uninitialized_returns_503():
    """Verify HTTP 503 is returned strictly when ML model is uninitialized or not trained."""
    with patch("backend.routers.predict.get_predictor") as mock_get_predictor:
        mock_predictor = MagicMock()
        mock_predictor._trained = False
        mock_get_predictor.return_value = mock_predictor
        
        response = client.post("/api/v1/predict", json={
            "origin": "DEL",
            "destination": "BOM",
            "departure_date": FUTURE_DATE
        })
        
        assert response.status_code == 503
        data = response.json()
        error_msg = data.get("error", {}).get("message") or data.get("detail", "")
        assert "No forecast model has been trained yet" in error_msg
