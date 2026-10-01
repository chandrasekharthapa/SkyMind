from openai import AsyncOpenAI
from .config import FirewallConfig

class NVIDIAClientProvider:
    """Provides a singleton-like managed instance of the AsyncOpenAI client for NVIDIA."""
    _client: AsyncOpenAI | None = None

    @classmethod
    def get_client(cls, config: FirewallConfig) -> AsyncOpenAI:
        if cls._client is None:
            if not config.nvidia_api_key:
                raise ValueError("NVIDIA_API_KEY is missing from configuration.")
            cls._client = AsyncOpenAI(
                base_url=config.nvidia_base_url,
                api_key=config.nvidia_api_key,
                # The guardrail wrapper owns retries and the timeout.
                max_retries=0,
            )
        return cls._client

    @classmethod
    def inject_client(cls, client: AsyncOpenAI | None) -> None:
        """Inject or clear the managed client (primarily for tests)."""
        cls._client = client

    @classmethod
    def reset_client(cls) -> None:
        """Clear process-global client state between independent operations."""
        cls._client = None


class GroqClientProvider:
    """The same, for Groq's OpenAI-compatible endpoint."""
    _client: AsyncOpenAI | None = None

    @classmethod
    def get_client(cls, config: FirewallConfig) -> AsyncOpenAI:
        if cls._client is None:
            if not config.groq_api_key:
                raise ValueError("GROQ_API_KEY is missing from configuration.")
            cls._client = AsyncOpenAI(
                base_url=config.groq_base_url,
                api_key=config.groq_api_key,
                max_retries=0,
            )
        return cls._client

    @classmethod
    def inject_client(cls, client: AsyncOpenAI | None) -> None:
        cls._client = client

    @classmethod
    def reset_client(cls) -> None:
        cls._client = None
