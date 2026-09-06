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
            )
        return cls._client

    @classmethod
    def inject_client(cls, client: AsyncOpenAI):
        """For dependency injection in unit tests."""
        cls._client = client
