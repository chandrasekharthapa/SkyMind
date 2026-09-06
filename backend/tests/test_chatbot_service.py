import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.chatbot_service import chatbot_service

@pytest.mark.asyncio
async def test_chatbot_service_stream_fallback(monkeypatch):
    """Verify chatbot_service falls back correctly on API failure."""
    # Force exception inside completions.create
    monkeypatch.setattr(
        chatbot_service.nvidia_client.chat.completions,
        "create",
        AsyncMock(side_effect=Exception("NVIDIA API timeout"))
    )

    chunks = []
    async for chunk in chatbot_service.chat_stream("test_sess", [{"role": "user", "content": "Flights to BOM"}]):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert b"Something went wrong" in chunks[0]
