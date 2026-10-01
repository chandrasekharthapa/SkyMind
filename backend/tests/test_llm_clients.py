"""Provider selection for the planner and judge (backend/services/llm_clients.py)."""

import pytest

from backend.services.llm_clients import NVIDIA_BASE_URL, parse_json_object, resolve


@pytest.fixture
def env(monkeypatch):
    for k in ("OPENAI_API_KEY", "NVIDIA_API_KEY", "PLANNER_PROVIDER", "JUDGE_PROVIDER",
              "PLANNER_MODEL", "JUDGE_MODEL", "OPENAI_MODEL_ID", "JUDGE_TIMEOUT_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_openai_key_keeps_the_old_behaviour(env):
    env.setenv("OPENAI_API_KEY", "sk-test")
    env.setenv("NVIDIA_API_KEY", "nv-test")
    assert resolve("PLANNER").provider == "openai"
    assert resolve("JUDGE").model == "gpt-4o-mini"


def test_without_openai_the_judge_uses_nvidia_and_the_planner_is_off(env):
    env.setenv("NVIDIA_API_KEY", "nv-test")
    judge = resolve("JUDGE")
    assert judge.provider == "nvidia" and str(judge.client.base_url).rstrip("/") == NVIDIA_BASE_URL
    assert judge.model == "openai/gpt-oss-20b"
    assert resolve("PLANNER") is None


def test_explicit_settings_win(env):
    env.setenv("OPENAI_API_KEY", "sk-test")
    env.setenv("NVIDIA_API_KEY", "nv-test")
    env.setenv("PLANNER_PROVIDER", "nvidia")
    env.setenv("PLANNER_MODEL", "nvidia/some-model")
    env.setenv("JUDGE_PROVIDER", "none")
    env.setenv("JUDGE_TIMEOUT_SECONDS", "9")
    planner = resolve("PLANNER")
    assert (planner.provider, planner.model, planner.supports_json_mode) == ("nvidia", "nvidia/some-model", False)
    assert resolve("JUDGE") is None


def test_provider_without_a_key_is_off(env):
    env.setenv("JUDGE_PROVIDER", "nvidia")
    assert resolve("JUDGE") is None


@pytest.mark.parametrize("text", [
    '{"decision": "PASS"}',
    'Here is my verdict:\n```json\n{"decision": "PASS"}\n```',
    'Sure! {"decision": "PASS"} Hope that helps.',
])
def test_parse_json_object_tolerates_wrappers(text):
    assert parse_json_object(text) == {"decision": "PASS"}


def test_parse_json_object_rejects_non_objects():
    with pytest.raises(ValueError):
        parse_json_object("no json here")


# ── Chat model chain and fallback ─────────────────────────────────────

import httpx
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from openai import APIStatusError, RateLimitError

from backend.services.chatbot_service import ChatbotService
from backend.services.llm_clients import ChatTarget, chat_targets


def _status_error(cls, status, text="err"):
    resp = httpx.Response(status, request=httpx.Request("POST", "https://x/v1/chat/completions"), text=text)
    return cls(text, response=resp, body=None)


@pytest.fixture
def chat_env(monkeypatch):
    for k in ("GROQ_API_KEY", "NVIDIA_API_KEY", "CHAT_MODELS", "CHAT_MODEL_ID"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_default_chain_is_open_models_first(chat_env):
    chat_env.setenv("GROQ_API_KEY", "gsk-test")
    chat_env.setenv("NVIDIA_API_KEY", "nv-test")
    labels = [t.label for t in chat_targets()]
    assert labels == ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b",
                      "nvidia:nvidia/nemotron-3-super-120b-a12b"]


def test_chain_skips_providers_without_a_key(chat_env):
    chat_env.setenv("NVIDIA_API_KEY", "nv-test")
    assert [t.label for t in chat_targets()] == ["nvidia:nvidia/nemotron-3-super-120b-a12b"]


def test_chat_models_override_and_legacy_model_id(chat_env):
    chat_env.setenv("GROQ_API_KEY", "gsk-test")
    chat_env.setenv("NVIDIA_API_KEY", "nv-test")
    chat_env.setenv("CHAT_MODELS", "nvidia:a/b, groq:c/d")
    assert [t.label for t in chat_targets()] == ["nvidia:a/b", "groq:c/d"]
    chat_env.delenv("CHAT_MODELS")
    chat_env.setenv("CHAT_MODEL_ID", "x/y")
    assert [t.label for t in chat_targets()] == ["nvidia:x/y"]


def _target(name, create):
    client = MagicMock()
    client.chat.completions.create = create
    return ChatTarget(provider=name, model=f"{name}-model", client=client)


async def test_rate_limited_model_hands_over_to_the_next():
    ok = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="hi", tool_calls=None))])
    first = AsyncMock(side_effect=_status_error(RateLimitError, 429))
    second = AsyncMock(return_value=ok)
    service = ChatbotService()
    service._targets = [_target("groq", first), _target("nvidia", second)]
    assert await service._complete(messages=[]) is ok
    assert second.call_args.kwargs["model"] == "nvidia-model"


@pytest.mark.parametrize("status, text", [(410, "gone"), (413, "Request too large: tokens per minute"),
                                          (400, "tool_use_failed: invalid tool call")])
async def test_other_recoverable_errors_fall_back(status, text):
    ok = SimpleNamespace(choices=[])
    service = ChatbotService()
    service._targets = [_target("groq", AsyncMock(side_effect=_status_error(APIStatusError, status, text))),
                        _target("nvidia", AsyncMock(return_value=ok))]
    assert await service._complete(messages=[]) is ok


async def test_a_genuine_bad_request_is_not_retried_elsewhere():
    second = AsyncMock()
    service = ChatbotService()
    service._targets = [_target("groq", AsyncMock(side_effect=_status_error(APIStatusError, 400, "bad schema"))),
                        _target("nvidia", second)]
    with pytest.raises(APIStatusError):
        await service._complete(messages=[])
    second.assert_not_called()


async def test_last_model_failure_is_raised():
    service = ChatbotService()
    service._targets = [_target("groq", AsyncMock(side_effect=_status_error(RateLimitError, 429))),
                        _target("nvidia", AsyncMock(side_effect=_status_error(RateLimitError, 429)))]
    with pytest.raises(RateLimitError):
        await service._complete(messages=[])
