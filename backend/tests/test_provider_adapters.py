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


def test_factory_fallback():
    """Assert unknown provider key falls back gracefully to NVIDIAAdapter."""
    provider = get_llm_provider("unknown_provider_xyz")
    assert isinstance(provider, NVIDIAAdapter)
