import pytest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.chat_response_validator import ChatResponseValidator

def test_validate_response_valid():
    tool_results = [
        {
            "status": "success",
            "flights": [{"price": 9330.0, "primary_airline": "6E", "flight_number": "6E101"}]
        }
    ]
    # Response contains exact returned price
    text = "We found a flight with IndiGo 6E101 for ₹9,330."
    assert ChatResponseValidator.validate_llm_response(text, tool_results) is True

def test_validate_response_hallucinated_price():
    tool_results = [
        {
            "status": "success",
            "flights": [{"price": 9330.0, "primary_airline": "6E", "flight_number": "6E101"}]
        }
    ]
    # Response contains fabricated price ₹15,500
    text = "We found a flight for ₹15,500 which is a great deal."
    assert ChatResponseValidator.validate_llm_response(text, tool_results) is False

def test_validate_response_hallucinated_keyword():
    tool_results = [
        {
            "status": "success",
            "flights": [{"price": 9330.0, "primary_airline": "6E", "flight_number": "6E101"}]
        }
    ]
    # Response contains free baggage hallucination
    text = "We found a flight for ₹9,330 which includes free baggage."
    assert ChatResponseValidator.validate_llm_response(text, tool_results) is False
