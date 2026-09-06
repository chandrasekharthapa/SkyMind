import pytest
import sys
import os
from unittest.mock import AsyncMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.chatbot_tools import execute_chatbot_tool
from backend.services.prediction_service import prediction_service

@pytest.mark.asyncio
async def test_predict_price_tool(monkeypatch):
    """Verify PricePredictionTool routes to PredictionService.predict."""
    mock_predict = AsyncMock(return_value={"predicted_price": 9300.0, "decision": {"decision": "BOOK NOW", "reasons": ["Rising trend"]}})
    monkeypatch.setattr(prediction_service, "predict", mock_predict)

    res = await execute_chatbot_tool(
        "predict_price",
        {"origin": "DEL", "destination": "BOM", "departure_date": "2026-07-26", "airline_code": None}
    )

    assert res["status"] == "success"
    assert res["predicted_price"] == 9300.0
    mock_predict.assert_called_once()
