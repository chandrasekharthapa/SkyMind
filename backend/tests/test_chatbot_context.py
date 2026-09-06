import pytest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.chatbot_service import ConversationContext

def test_conversation_context_update():
    context = ConversationContext()
    
    # 1. First search call updates context
    context.update_from_args({
        "origin": "DEL",
        "destination": "BOM",
        "departure_date": "2026-07-26"
    })
    
    assert context.origin == "DEL"
    assert context.destination == "BOM"
    assert context.departure_date == "2026-07-26"
    assert context.airline_code is None

    # 2. Second follow-up query updates only airline
    context.update_from_args({
        "airline_code": "AI"
    })
    
    assert context.origin == "DEL"  # retained previous state
    assert context.destination == "BOM"
    assert context.airline_code == "AI"
