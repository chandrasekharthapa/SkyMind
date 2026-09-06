import pytest
import pytest_asyncio
import os
import yaml
from unittest.mock import AsyncMock, patch, MagicMock

from backend.firewall.config import FirewallConfig
from backend.firewall.models import GuardrailResult, GuardrailStatus
from backend.firewall.client import NVIDIAClientProvider
from backend.firewall.context import RequestContext
from backend.firewall.pipeline.pipeline import PolicyPlatform
from backend.firewall.config_loader import PolicyLoader
from backend.firewall.rules.models import RuleAction

@pytest.fixture
def config():
    return FirewallConfig(
        timeout=1.0,
        retry_count=1,
        retry_backoff=0.1,
        concurrency_limit=2,
        fail_open=False,
        nvidia_api_key="test-key"
    )

@pytest.fixture
def policy_file(tmp_path):
    policy_path = tmp_path / "policy.yaml"
    policy_data = {
        "version": "2.0",
        "default_action": "ALLOW",
        "rules": [
            {
                "id": "test_block",
                "priority": 100,
                "enabled": True,
                "match": {
                    "verdict": "UNSAFE"
                },
                "action": "BLOCK"
            }
        ]
    }
    with open(policy_path, "w") as f:
        yaml.dump(policy_data, f)
    return str(policy_path)

@pytest.mark.asyncio
async def test_policy_platform_safe(config, policy_file):
    # Mock the AsyncOpenAI client
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="safe"))]
    mock_client.chat.completions.create.return_value = mock_response
    
    # Inject mock
    NVIDIAClientProvider.inject_client(mock_client)
    
    loader = PolicyLoader(file_path=policy_file)
    platform = PolicyPlatform(config=config, policy_loader=loader)
    
    context = await platform.evaluate_messages([{"role": "user", "content": "test safe prompt"}])
    
    assert context.decision is not None
    assert context.decision.is_safe is True
    assert len(context.decision.violations) == 0
    assert context.risk_score == 0.0

@pytest.mark.asyncio
async def test_policy_platform_unsafe(config, policy_file):
    # Mock the AsyncOpenAI client
    mock_client = AsyncMock()
    mock_response = MagicMock()
    # Mock returning unsafe
    mock_response.choices = [MagicMock(message=MagicMock(content="unsafe"))]
    mock_client.chat.completions.create.return_value = mock_response
    
    NVIDIAClientProvider.inject_client(mock_client)
    
    loader = PolicyLoader(file_path=policy_file)
    platform = PolicyPlatform(config=config, policy_loader=loader)
    
    context = await platform.evaluate_messages([{"role": "user", "content": "test unsafe prompt"}])
    
    assert context.decision is not None
    assert context.decision.is_safe is False
    assert len(context.decision.violations) > 0
    # Guardrails will all return unsafe, so risk score will be max (100)
    assert context.risk_score == 100.0
