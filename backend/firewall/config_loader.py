"""Loads and watches the firewall's rule policy.

Two defects lived here, and the user's own boot log printed the first one:

    Policy file policy.yaml not found. Using default policy.

`routers/chat.py` and `services/agent_graph.py` both constructed this loader with
`file_path="policy.yaml"` — a path relative to the process's working directory. The
API's only launchable form is `python -m uvicorn backend.main:app` from the
repository root (`backend/__init__.py` is absent, so launching from inside
`backend/` breaks `main.py`'s `backend.ml.price_model` import), and the policy file
lives at `backend/policy.yaml`. So the path resolved to a file that has never
existed, on every launch.

The second defect is what happened next. A missing file substituted
`PolicyConfig()`: `default_action: ALLOW` and `rules: []`. With no rules,
`RuleEngine.evaluate` leaves `final_action` at the default and computes
`is_safe = final_action != BLOCK`, so `is_safe` was unconditionally True — and
`routers/chat.py` gates interception on `not decision.is_safe`. The guardrails still
ran, still returned UNSAFE, and still populated `decision.violations`; every
violation was then allowed through. The shipped rules that do the blocking —
`jailbreak_block`, `content_block`, `topic_block`, `high_risk_block` — were loaded
in no deployment. A firewall that detects and permits is worse than no firewall,
because the audit log records the detection and the request proceeds anyway.

The default path is now resolved from `__file__`, which is what
`governance/engine.py` already did, and an absent or unparseable policy is refused
at construction rather than replaced with a permissive one. A *later* hot-reload
failure keeps the last policy that did load — the one behaviour here that was
already right.
"""

import os
import threading
import logging
from pathlib import Path
from typing import Optional, Union

import yaml

from backend.firewall.rules.models import PolicyConfig

logger = logging.getLogger(__name__)

# `backend/policy.yaml`, resolved from this file rather than from the working
# directory of whatever process happens to import it.
DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "policy.yaml"


class PolicyLoader:
    """Loads and watches a YAML configuration file for the policy engine."""

    def __init__(self, file_path: Union[str, os.PathLike, None] = None):
        self.file_path = (
            Path(file_path) if file_path is not None else DEFAULT_POLICY_PATH)
        self._current_policy: Optional[PolicyConfig] = None
        self._last_mtime: float = 0.0
        self._lock = threading.Lock()

        # Initial load. This raises if the policy cannot be read: a firewall with
        # no rules admits everything its guardrails flag, so failing to start is
        # the safer outcome than starting permissive.
        self._current_policy = self._read_policy()
        self._last_mtime = self.file_path.stat().st_mtime
        if self._current_policy.rules:
            logger.info(
                "Firewall policy loaded from %s (%d rule(s))",
                self.file_path, len(self._current_policy.rules))
        else:
            # A file that exists and declares no rules is an operator's explicit
            # choice, unlike a file that is absent, so this warns instead of
            # raising — but it names the consequence, because the consequence is
            # that nothing gets blocked.
            logger.warning(
                "Firewall policy at %s declares no rules. Every request will take "
                "default_action=%s, including ones the guardrails flag as UNSAFE.",
                self.file_path, self._current_policy.default_action.value)

    def _read_policy(self) -> PolicyConfig:
        """Parse the policy file, raising rather than returning a permissive default."""
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"Firewall policy not found at {self.file_path}. Refusing to run "
                f"with no rules loaded: an empty policy allows every request the "
                f"guardrails flag as unsafe.")
        with self.file_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not data:
            raise ValueError(
                f"Firewall policy at {self.file_path} parsed as empty. Refusing to "
                f"run with no rules loaded.")
        return PolicyConfig(**data)

    def get_policy(self) -> PolicyConfig:
        """Returns the current policy, reloading it if the file changed."""
        self.reload_if_changed()
        return self._current_policy

    def reload_if_changed(self) -> None:
        """Reload on mtime change, keeping the last good policy on any failure."""
        try:
            current_mtime = self.file_path.stat().st_mtime
        except OSError as exc:
            # Readable at construction, not readable now. Keep serving the policy
            # that did load; do not substitute a permissive one.
            logger.error(
                "Firewall policy at %s is no longer readable (%s). Continuing with "
                "the last policy that loaded.", self.file_path, exc)
            return

        if current_mtime <= self._last_mtime:
            return

        with self._lock:
            # Re-check inside the lock to prevent duplicate reloads.
            if current_mtime <= self._last_mtime:
                return
            # Advance the marker before parsing, so a policy that fails to parse
            # is reported once per edit rather than once per request.
            self._last_mtime = current_mtime
            try:
                policy = self._read_policy()
            except Exception as exc:
                logger.error(
                    "Firewall policy reload from %s failed (%s). Continuing with "
                    "the last policy that loaded.", self.file_path, exc)
                return
            self._current_policy = policy
            logger.info(
                "Firewall policy reloaded from %s (%d rule(s))",
                self.file_path, len(policy.rules))
