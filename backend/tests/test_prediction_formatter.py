import pytest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.prediction_formatter import PredictionFormatter

def test_calculate_trend_rising():
    forecast = [
        {"day": 1, "date": "2026-07-20", "price": 10000.0, "lower": 9000.0, "upper": 11000.0},
        {"day": 2, "date": "2026-07-21", "price": 11000.0, "lower": 9900.0, "upper": 12100.0}
    ]
    trend, change, prob = PredictionFormatter.calculate_trend(forecast)
    assert trend == "RISING"
    assert change == 10.0
    assert prob > 0.5

def test_calculate_trend_falling():
    forecast = [
        {"day": 1, "date": "2026-07-20", "price": 10000.0, "lower": 9000.0, "upper": 11000.0},
        {"day": 2, "date": "2026-07-21", "price": 9000.0, "lower": 8100.0, "upper": 9900.0}
    ]
    trend, change, prob = PredictionFormatter.calculate_trend(forecast)
    assert trend == "FALLING"
    assert change == -10.0
    assert prob < 0.5

def test_compute_market_status():
    prices = [10000.0, 10100.0, 9900.0, 10200.0, 9800.0]
    status = PredictionFormatter.compute_market_status(prices)
    # Low standard deviation / average ratio -> STABLE
    assert status == "STABLE"

    volatile_prices = [10000.0, 15000.0, 5000.0, 12000.0, 8000.0]
    status_volatile = PredictionFormatter.compute_market_status(volatile_prices)
    assert status_volatile == "VOLATILE"
