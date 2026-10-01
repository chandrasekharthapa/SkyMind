"""Model endpoints for the chatbot's helper agents (planner and judge).

Both used to be hard-wired to OpenAI's gpt-4o-mini. The OpenAI account behind
this project has been out of quota since at least July 2026 (the eval report of
2026-07-27 records `insufficient_quota`), so in production the planner always
fell back to its rule-based mode and the judge never ran. These helpers let each
role use OpenAI, NVIDIA's hosted open models (the same endpoint and key as the
chat model), or nothing.

    PLANNER_PROVIDER / JUDGE_PROVIDER = openai | nvidia | none
    PLANNER_MODEL    / JUDGE_MODEL    = model id for that provider
    PLANNER_TIMEOUT_SECONDS / JUDGE_TIMEOUT_SECONDS

Defaults keep the old behaviour where it still works: OpenAI when an
OPENAI_API_KEY is set. Without one, the judge uses NVIDIA (it runs rarely, so a
slower open model is affordable) and the planner is off — it is advisory, the
chat model chooses its own tools, and an extra model round-trip on every turn
costs more latency than the planner's hint is worth. The rule-based planner
still runs either way.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

_DEFAULT_MODELS = {
    ("PLANNER", "openai"): "gpt-4o-mini",
    ("PLANNER", "nvidia"): "openai/gpt-oss-20b",
    ("JUDGE", "openai"): "gpt-4o-mini",
    # A different model from the one whose answers it grades.
    ("JUDGE", "nvidia"): "openai/gpt-oss-20b",
}
_DEFAULT_TIMEOUTS = {
    ("PLANNER", "openai"): 3.0, ("PLANNER", "nvidia"): 8.0,
    ("JUDGE", "openai"): 4.0, ("JUDGE", "nvidia"): 20.0,
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

    default = "openai" if openai_key else ("nvidia" if role == "JUDGE" and nvidia_key else "none")
    provider = os.getenv(f"{role}_PROVIDER", default).strip().lower()

    if provider == "openai" and openai_key:
        client = AsyncOpenAI(api_key=openai_key)
    elif provider == "nvidia" and nvidia_key:
        client = AsyncOpenAI(base_url=NVIDIA_BASE_URL, api_key=nvidia_key)
    else:
        return None

    # OPENAI_MODEL_ID was the old shared override; it still applies to OpenAI.
    model = (
        os.getenv(f"{role}_MODEL")
        or (os.getenv("OPENAI_MODEL_ID") if provider == "openai" else None)
        or _DEFAULT_MODELS[(role, provider)]
    )
    timeout = float(os.getenv(f"{role}_TIMEOUT_SECONDS", _DEFAULT_TIMEOUTS[(role, provider)]))
    return LLMTarget(provider=provider, model=model, client=client, timeout=timeout)


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
