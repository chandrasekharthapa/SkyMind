import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.services.chatbot_service import ChatbotService


@pytest.mark.asyncio
async def test_chatbot_service_stream_fallback():
    """Verify chatbot_service falls back correctly on API failure."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=Exception("NVIDIA API timeout")
    )
    service = ChatbotService(nvidia_client=mock_client)

    chunks = []
    async for chunk in service.chat_stream(
        "test_sess", [{"role": "user", "content": "Flights to BOM"}]
    ):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert b"Something went wrong" in chunks[0]
