"""Test Suite for Optimal Booking Window Logic."""

import pytest
from backend.services.recommendation_engine import recommendation_engine


def test_optimal_booking_window_case1_lowest_today():
    """Case 1: Lowest price today -> BUY NOW, horizon 0."""
    forecast = [
        {"day": 0, "date": "2026-07-23", "price": 6283},
        {"day": 1, "date": "2026-07-24", "price": 6400},
        {"day": 3, "date": "2026-07-26", "price": 6500},
        {"day": 7, "date": "2026-07-30", "price": 6700},
    ]
    opt = recommendation_engine.compute_optimal_booking_window(forecast, current_lowest=6283)
    assert opt["prediction_horizon"] == 0
    assert opt["booking_date"] == "2026-07-23"
    assert opt["expected_price"] == 6283
    assert opt["estimated_savings"] == 0
    assert opt["recommendation"] == "BUY NOW"


def test_optimal_booking_window_case2_lowest_tomorrow():
    """Case 2: Lowest price tomorrow -> WAIT, horizon 1."""
    forecast = [
        {"day": 0, "date": "2026-07-23", "price": 6283},
        {"day": 1, "date": "2026-07-24", "price": 6100},
        {"day": 3, "date": "2026-07-26", "price": 6200},
        {"day": 7, "date": "2026-07-30", "price": 6400},
    ]
    opt = recommendation_engine.compute_optimal_booking_window(forecast, current_lowest=6283)
    assert opt["prediction_horizon"] == 1
    assert opt["booking_date"] == "2026-07-24"
    assert opt["expected_price"] == 6100
    assert opt["estimated_savings"] == 183
    assert opt["recommendation"] == "WAIT"


def test_optimal_booking_window_case3_lowest_day3():
    """Case 3: Lowest price Day 3 -> WAIT 3 DAYS."""
    forecast = [
        {"day": 0, "date": "2026-07-23", "price": 6283},
        {"day": 1, "date": "2026-07-24", "price": 6120},
        {"day": 3, "date": "2026-07-26", "price": 5794},
        {"day": 7, "date": "2026-07-30", "price": 6041},
    ]
    opt = recommendation_engine.compute_optimal_booking_window(forecast, current_lowest=6283)
    assert opt["prediction_horizon"] == 3
    assert opt["booking_date"] == "2026-07-26"
    assert opt["expected_price"] == 5794
    assert opt["estimated_savings"] == 489
    assert opt["percentage_savings"] == 7.8
    assert opt["recommendation"] == "WAIT"


def test_optimal_booking_window_case4_lowest_day7():
    """Case 4: Lowest price Day 7 -> WAIT 7 DAYS."""
    forecast = [
        {"day": 0, "date": "2026-07-23", "price": 6283},
        {"day": 1, "date": "2026-07-24", "price": 6200},
        {"day": 3, "date": "2026-07-26", "price": 6100},
        {"day": 7, "date": "2026-07-30", "price": 5600},
    ]
    opt = recommendation_engine.compute_optimal_booking_window(forecast, current_lowest=6283)
    assert opt["prediction_horizon"] == 7
    assert opt["booking_date"] == "2026-07-30"
    assert opt["expected_price"] == 5600
    assert opt["estimated_savings"] == 683
    assert opt["recommendation"] == "WAIT"


def test_optimal_booking_window_case5_tie_breaking():
    """Case 5: Tie-breaking selects earliest horizon (horizon 0/Today)."""
    forecast = [
        {"day": 0, "date": "2026-07-23", "price": 5794},
        {"day": 1, "date": "2026-07-24", "price": 5794},
        {"day": 3, "date": "2026-07-26", "price": 5794},
        {"day": 7, "date": "2026-07-30", "price": 6000},
    ]
    opt = recommendation_engine.compute_optimal_booking_window(forecast, current_lowest=5794)
    assert opt["prediction_horizon"] == 0
    assert opt["booking_date"] == "2026-07-23"
    assert opt["recommendation"] == "BUY NOW"
    assert opt["estimated_savings"] == 0
