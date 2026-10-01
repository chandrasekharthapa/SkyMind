"""Model endpoints for the chatbot's helper agents (planner and judge).

Both used to be hard-wired to OpenAI's gpt-4o-mini. The OpenAI account behind
this project has been out of quota since at least July 2026, and while
OPENAI_API_KEY stayed set on Render every chat turn spent ~5 s on a planner call
that could only fail (the SDK retried the 429 twice before giving up). These
helpers let each role use Groq, OpenAI, NVIDIA's hosted open models, or nothing.

    PLANNER_PROVIDER / JUDGE_PROVIDER = groq | openai | nvidia | none
    PLANNER_MODEL    / JUDGE_MODEL    = model id for that provider
    PLANNER_TIMEOUT_SECONDS / JUDGE_TIMEOUT_SECONDS

Defaults, when *_PROVIDER is unset: Groq if GROQ_API_KEY is set (sub-second, so
the planner's hint is cheap), else OpenAI if OPENAI_API_KEY is set, else the
judge uses NVIDIA and the planner is off. The rule-based planner runs either way.

Helper calls make no SDK retries: the planner has a 3 s budget and the judge is
optional, so a failure should cost one round-trip, not three. A failure that
cannot fix itself (no credits, bad key, model gone — see is_permanent_failure)
switches the helper off for the rest of the process.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# provider -> (base_url, env var holding its key). base_url None = OpenAI's default.
PROVIDERS = {
    "groq": (GROQ_BASE_URL, "GROQ_API_KEY"),
    "nvidia": (NVIDIA_BASE_URL, "NVIDIA_API_KEY"),
    "openai": (None, "OPENAI_API_KEY"),
}

_DEFAULT_MODELS = {
    ("PLANNER", "openai"): "gpt-4o-mini",
    ("PLANNER", "nvidia"): "openai/gpt-oss-20b",
    ("JUDGE", "openai"): "gpt-4o-mini",
    # A different model from the one whose answers it grades.
    ("JUDGE", "nvidia"): "openai/gpt-oss-20b",
    ("PLANNER", "groq"): "openai/gpt-oss-20b",
    ("JUDGE", "groq"): "openai/gpt-oss-20b",
}
_DEFAULT_TIMEOUTS = {
    ("PLANNER", "openai"): 3.0, ("PLANNER", "nvidia"): 8.0,
    ("JUDGE", "openai"): 4.0, ("JUDGE", "nvidia"): 20.0,
    ("PLANNER", "groq"): 3.0, ("JUDGE", "groq"): 8.0,
}


@dataclass
class LLMTarget:
    provider: str
    model: str
    client: AsyncOpenAI
    timeout: float

    @property
    def supports_json_mode(self) -> bool:
        # OpenAI honours response_format={"type": "json_object"}; NVIDIA's hosted
        # models do not reliably, so for them the JSON is extracted from the text.
        return self.provider == "openai"


def resolve(role: str) -> Optional[LLMTarget]:
    """The endpoint for `role` ("PLANNER" or "JUDGE"), or None if it is off or
    has no key."""
    role = role.upper()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()

    groq_key = os.getenv("GROQ_API_KEY", "").strip()

    if groq_key:
        default = "groq"
    elif openai_key:
        default = "openai"
    elif role == "JUDGE" and nvidia_key:
        default = "nvidia"
    else:
        default = "none"
    provider = os.getenv(f"{role}_PROVIDER", default).strip().lower()

    client = _client_for(provider, max_retries=0)
    if client is None:
        return None

    # OPENAI_MODEL_ID was the old shared override; it still applies to OpenAI.
    model = (
        os.getenv(f"{role}_MODEL")
        or (os.getenv("OPENAI_MODEL_ID") if provider == "openai" else None)
        or _DEFAULT_MODELS[(role, provider)]
    )
    timeout = float(os.getenv(f"{role}_TIMEOUT_SECONDS", _DEFAULT_TIMEOUTS[(role, provider)]))
    return LLMTarget(provider=provider, model=model, client=client, timeout=timeout)


def _client_for(provider: str, timeout: Optional[float] = None, max_retries: int = 2) -> Optional[AsyncOpenAI]:
    if provider not in PROVIDERS:
        return None
    base_url, key_env = PROVIDERS[provider]
    key = os.getenv(key_env, "").strip()
    if not key:
        return None
    kwargs: Dict[str, Any] = {"api_key": key, "max_retries": max_retries}
    if base_url:
        kwargs["base_url"] = base_url
    if timeout is not None:
        kwargs["timeout"] = timeout
    return AsyncOpenAI(**kwargs)


def is_permanent_failure(exc: Exception) -> bool:
    """True for errors that retrying will not fix: an account with no credits,
    a rejected key, or a model the provider has removed."""
    status = getattr(exc, "status_code", None)
    if status in (401, 403, 404, 410):
        return True
    text = str(exc)
    return status == 429 and ("insufficient_quota" in text or "credit_balance_exhausted" in text)


@dataclass
class ChatTarget:
    provider: str
    model: str
    client: AsyncOpenAI

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


# The chat model chain, tried in order (2026-10-01 comparison, scratch/compare_open_models.py):
#   groq:openai/gpt-oss-120b   9/9, 0.7 s median, Apache-2.0
#   groq:openai/gpt-oss-20b    9/9, 0.6 s median, Apache-2.0 — separate rate-limit bucket
#   nvidia:nvidia/nemotron-3-super-120b-a12b   9/9, 4.1 s median — last resort
# Groq's free tier allows 8K tokens/minute and 200K/day per model, roughly one chat
# turn a minute; the chain is what keeps the chatbot answering past that.
DEFAULT_CHAT_CHAIN = [
    ("groq", "openai/gpt-oss-120b"),
    ("groq", "openai/gpt-oss-20b"),
    ("nvidia", "nvidia/nemotron-3-super-120b-a12b"),
]


def chat_targets() -> List[ChatTarget]:
    """The chat models to try, in order, skipping any whose provider has no key.

    CHAT_MODELS overrides the chain: comma-separated provider:model entries, e.g.
    "groq:openai/gpt-oss-120b,nvidia:nvidia/nemotron-3-super-120b-a12b".
    CHAT_MODEL_ID alone (the earlier single-model setting) puts that NVIDIA model
    first, ahead of the default chain.
    """
    spec = os.getenv("CHAT_MODELS", "").strip()
    if spec:
        chain = []
        for part in spec.split(","):
            provider, _, model = part.strip().partition(":")
            if provider and model:
                chain.append((provider.lower(), model))
    elif os.getenv("CHAT_MODEL_ID", "").strip():
        # The earlier single-model setting. It goes first, but the default chain
        # still backs it up: on Render it was left pointing at
        # meta/llama-3.1-70b-instruct after NVIDIA retired that model, and with
        # it as the only entry every chat turn failed.
        legacy = ("nvidia", os.getenv("CHAT_MODEL_ID").strip())
        chain = [legacy] + [entry for entry in DEFAULT_CHAT_CHAIN if entry != legacy]
    else:
        chain = DEFAULT_CHAT_CHAIN

    timeout = float(os.getenv("CHAT_TIMEOUT_SECONDS", "45"))
    targets = []
    for provider, model in chain:
        # No client-side retries: a rate-limited or failing model should hand
        # over to the next one immediately, not after the SDK's backoff.
        client = _client_for(provider, timeout=timeout, max_retries=0)
        if client is None:
            logger.info(f"[llm_clients] Skipping chat model {provider}:{model}: no API key for {provider}.")
            continue
        targets.append(ChatTarget(provider=provider, model=model, client=client))
    if not targets:
        logger.error("[llm_clients] No chat model is usable: set GROQ_API_KEY or NVIDIA_API_KEY.")
    return targets


def parse_json_object(text: str) -> Dict[str, Any]:
    """The first JSON object in `text`. Open models often wrap JSON in prose or a
    ```json fence; OpenAI's JSON mode returns it bare."""
    text = (text or "").strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model output")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model output JSON is not an object")
    return value
