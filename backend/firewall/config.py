import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class FirewallConfig(BaseSettings):
    """Configuration for the firewall service. Every field can be set from the
    environment with a FIREWALL_ prefix (e.g. FIREWALL_TIMEOUT=2)."""
    # Timeout in seconds for individual guardrail evaluation
    timeout: float = 3.0

    # Attempts per guardrail per request. One: the guardrails run inline on every
    # chat turn, and a second attempt at a slow or failing endpoint doubled the
    # wait (three NVIDIA guardrails failing at once cost ~7 s per message).
    retry_count: int = 1
    retry_backoff: float = 0.5

    # After this many consecutive errors a guardrail is skipped (reported as
    # ERROR straight away, which fail_open then decides) for breaker_recovery_seconds,
    # then tried again. Keeps a dead model from adding its timeout to every turn.
    breaker_threshold: int = 3
    breaker_recovery_seconds: float = 300.0

    # Concurrency limit for asyncio.Semaphore to prevent API rate limiting
    concurrency_limit: int = 10

    # If True, firewall defaults to SAFE on unhandled API errors or timeouts
    fail_open: bool = True

    # NVIDIA API key
    nvidia_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    # Groq hosts Meta's Llama Prompt Guard 2, which replaces NVIDIA's
    # nemoguard-jailbreak-detect (removed from NVIDIA's API: it now answers 404).
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Models. The jailbreak check uses Groq's Prompt Guard when a Groq key is set,
    # and NVIDIA's model otherwise.
    jailbreak_model_groq: str = "meta-llama/llama-prompt-guard-2-86m"
    jailbreak_model_nvidia: str = "nvidia/nemoguard-jailbreak-detect"
    # Prompt Guard returns a probability that the text is an attack. High, because
    # flight requests are full of instruction-like phrasing ("ignore my last
    # search, show Goa instead") and a block here refuses a real customer.
    jailbreak_threshold: float = 0.8
    content_model: str = "nvidia/llama-3.1-nemoguard-8b-content-safety"
    topic_model: str = "nvidia/llama-3.1-nemoguard-8b-topic-control"

    model_config = SettingsConfigDict(env_prefix="FIREWALL_")
