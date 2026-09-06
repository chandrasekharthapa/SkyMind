"""Governance Policy Loader with hot-reload.

Loads ``backend/governance/policy.yaml`` and watches for file changes.
Provides a ``get_action(domain_str)`` method that returns a
``GovernanceDecision`` based on the loaded policy.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path

import yaml

from .models import GovernanceActionEnum, GovernanceDecision, DomainEnum, IntentEnum, ScopeEnum

logger = logging.getLogger(__name__)


class GovernancePolicyLoader:
    """Loads ``policy.yaml`` and watches for file changes."""

    def __init__(self, file_path: str | os.PathLike | None = None):
        if file_path is None:
            # Default: look relative to this file's directory
            file_path = Path(__file__).parent / "policy.yaml"
        self.file_path = Path(file_path)
        self._last_mtime = 0.0
        self._policy_data: dict = {}
        self._load_policy()

    def _load_policy(self) -> None:
        if not self.file_path.exists():
            logger.warning(f"Governance policy file not found: {self.file_path}")
            self._policy_data = {}
            return
        try:
            mtime = self.file_path.stat().st_mtime
            if mtime != self._last_mtime:
                with self.file_path.open("r", encoding="utf-8") as f:
                    self._policy_data = yaml.safe_load(f) or {}
                self._last_mtime = mtime
                logger.info(f"Governance policy loaded from {self.file_path}")
        except Exception as e:
            logger.error(f"Failed to load governance policy: {e}")

    def source_identifier(self) -> str:
        return str(self.file_path)

    def get_action(self, domain: str) -> GovernanceDecision:
        """Return a GovernanceDecision for the given domain string.

        Looks up the domain key in the policy YAML's ``domain:`` section.
        Falls back to ``unknown`` if the domain is not found.
        """
        self._load_policy()

        # Normalize: accept both DomainEnum objects and plain strings
        domain_key = domain.value if isinstance(domain, DomainEnum) else str(domain)

        domain_cfg = self._policy_data.get("domain", {}).get(domain_key, {})

        # If domain not in policy, fall back to "unknown"
        if not domain_cfg:
            domain_cfg = self._policy_data.get("domain", {}).get("unknown", {})

        raw_action = domain_cfg.get("action", "REFUSE")
        action = GovernanceActionEnum(raw_action)
        acknowledgement = domain_cfg.get("acknowledgement")
        redirect_target = domain_cfg.get("redirect_target")

        # Map domain_key back to a DomainEnum for the decision
        try:
            domain_enum = DomainEnum(domain_key)
        except ValueError:
            domain_enum = DomainEnum.UNKNOWN

        return GovernanceDecision(
            domain=domain_enum,
            intent=IntentEnum.UNKNOWN,
            scope=ScopeEnum.IN_SCOPE if action == GovernanceActionEnum.ALLOW else ScopeEnum.HARD_OFF_TOPIC,
            action=action,
            confidence=0.95,
            acknowledgement=acknowledgement,
            redirect_target=redirect_target,
        )


__all__ = ["GovernancePolicyLoader"]
