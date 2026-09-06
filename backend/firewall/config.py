import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class FirewallConfig(BaseSettings):
    """Configuration for the firewall service."""
    # Timeout in seconds for individual guardrail evaluation
    timeout: float = 3.0
    
    # Retry configurations for tenacity
    retry_count: int = 2
    retry_backoff: float = 0.5
    
    # Concurrency limit for asyncio.Semaphore to prevent API rate limiting
    concurrency_limit: int = 10
    
    # If True, firewall defaults to SAFE on unhandled API errors or timeouts
    fail_open: bool = True
    
    # NVIDIA API key
    nvidia_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    
    model_config = SettingsConfigDict(env_prefix="FIREWALL_")
