import pytest
import os
import sys
from pathlib import Path

# Add backend to sys.path so we can import packages correctly
sys.path.append(str(Path(__file__).parent.parent))

from backend.governance.classifier import classify_message
from backend.governance.engine import GovernancePolicyLoader
from backend.governance.models import DomainEnum, GovernanceActionEnum


@pytest.fixture
def policy_loader():
    # Instantiates the GovernancePolicyLoader which reads policy.yaml relative to its package path
    return GovernancePolicyLoader()


@pytest.mark.parametrize(
    "query, expected_domain, expected_action, expected_ack",
    [
        ("Hi", DomainEnum.GREETING, GovernanceActionEnum.ALLOW, None),
        ("Hello", DomainEnum.GREETING, GovernanceActionEnum.ALLOW, None),
        (
            "I am sad",
            DomainEnum.EMOTIONAL,
            GovernanceActionEnum.REDIRECT,
            "I'm sorry you're feeling that way. I'm here to help with flights and travel planning.",
        ),
        (
            "I love Vanshika",
            DomainEnum.PERSONAL,
            GovernanceActionEnum.REDIRECT,
            "That's nice to hear. If you need help planning a trip or finding flights, I'd be happy to help.",
        ),
        (
            "My girlfriend",
            DomainEnum.PERSONAL,
            GovernanceActionEnum.REDIRECT,
            "That's nice to hear. If you need help planning a trip or finding flights, I'd be happy to help.",
        ),
        (
            "Tell me a joke",
            DomainEnum.ENTERTAINMENT,
            GovernanceActionEnum.REDIRECT,
            "I'm focused on aviation and travel. Feel free to ask about flights, airlines, airports, or airfare trends.",
        ),
        (
            "Write Python",
            DomainEnum.PROGRAMMING,
            GovernanceActionEnum.REDIRECT,
            "I specialize in aviation and travel assistance. Ask me about flights, airports, airlines, or trip planning.",
        ),
        (
            "Who is Modi",
            DomainEnum.POLITICS,
            GovernanceActionEnum.REDIRECT,
            "I’m focused on aviation insights and can’t discuss politics. Ask me about flight routes instead.",
        ),
        (
            "What's Bitcoin",
            DomainEnum.FINANCE,
            GovernanceActionEnum.REDIRECT,
            "I’m here for aviation and travel queries only. Ask me about flight prices or trends.",
        ),
        ("Find flights to Delhi", DomainEnum.AVIATION, GovernanceActionEnum.ALLOW, None),
        ("Predict flight price", DomainEnum.AVIATION, GovernanceActionEnum.ALLOW, None),
        ("Show trends", DomainEnum.AVIATION, GovernanceActionEnum.ALLOW, None),
    ],
)
def test_governance_flow_regression(
    policy_loader, query, expected_domain, expected_action, expected_ack
):
    """Automatically verify classification and policy routing for all required queries."""
    classification = classify_message(query)
    assert (
        classification.domain == expected_domain
    ), f"Query '{query}' expected domain {expected_domain}, but got {classification.domain}"

    decision = policy_loader.get_action(classification.domain)
    assert (
        decision.action == expected_action
    ), f"Query '{query}' expected action {expected_action}, but got {decision.action}"

    if expected_ack is not None:
        assert (
            decision.acknowledgement == expected_ack
        ), f"Query '{query}' expected acknowledgement '{expected_ack}', but got '{decision.acknowledgement}'"
    else:
        assert (
            decision.acknowledgement is None or decision.acknowledgement == ""
        )
