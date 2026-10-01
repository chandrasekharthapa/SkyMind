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
