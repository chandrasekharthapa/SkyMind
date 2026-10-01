import pytest
import sys
import os
from unittest.mock import AsyncMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# A departure date that is always in the future. These tests hard-coded
# "2026-07-26", which has since passed; execute_chatbot_tool now refuses past
# departure dates (see prepare_tool_args), so a fixed date would rot.
from datetime import date as _date, timedelta as _timedelta
FUTURE_DATE = (_date.today() + _timedelta(days=30)).isoformat()

from backend.services.chatbot_tools import execute_chatbot_tool
from backend.services.prediction_service import prediction_service

@pytest.mark.asyncio
async def test_predict_price_tool(monkeypatch):
    """Verify PricePredictionTool routes to PredictionService.predict."""
    mock_predict = AsyncMock(return_value={"predicted_price": 9300.0, "decision": {"decision": "BOOK NOW", "reasons": ["Rising trend"]}})
    monkeypatch.setattr(prediction_service, "predict", mock_predict)

    res = await execute_chatbot_tool(
        "predict_price",
        {"origin": "DEL", "destination": "BOM", "departure_date": FUTURE_DATE, "airline_code": None}
    )

    assert res["status"] == "success"
    assert res["predicted_price"] == 9300.0
    mock_predict.assert_called_once()
