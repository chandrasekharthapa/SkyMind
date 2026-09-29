import pytest
from backend.services.llm_provider import (
    get_llm_provider,
    NVIDIAAdapter,
    OpenAIAdapter,
    AnthropicAdapter,
    GoogleAdapter,
    LocalAdapter,
    LLMProvider
)


def test_factory_default_provider():
    """Assert factory defaults to NVIDIAAdapter."""
    provider = get_llm_provider()
    assert isinstance(provider, NVIDIAAdapter)
    assert isinstance(provider, LLMProvider)


def test_factory_named_providers():
    """Assert factory resolves named provider keys correctly."""
    assert isinstance(get_llm_provider("openai"), OpenAIAdapter)
    assert isinstance(get_llm_provider("anthropic"), AnthropicAdapter)
    assert isinstance(get_llm_provider("google"), GoogleAdapter)
    assert isinstance(get_llm_provider("local"), LocalAdapter)
    assert isinstance(get_llm_provider("nvidia"), NVIDIAAdapter)


def test_factory_rejects_unknown_provider():
    """An invalid provider name must not silently send data to NVIDIA."""
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_provider("unknown_provider_xyz")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "message"),
    [
        (AnthropicAdapter(), "Anthropic streaming is not implemented"),
        (GoogleAdapter(), "Google Gemini streaming is not implemented"),
    ],
)
async def test_unimplemented_streams_fail_explicitly(adapter, message):
    """Unimplemented adapters must not emit a fabricated successful response."""
    stream = adapter.generate_stream([{"role": "user", "content": "hello"}])
    with pytest.raises(NotImplementedError, match=message):
        await anext(stream)
