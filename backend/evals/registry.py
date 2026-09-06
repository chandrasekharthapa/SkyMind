"""Evaluator Registry for SkyMind Copilot Evaluation Platform.

Supports evaluator self-registration and explicit infrastructure/evaluator statuses:
PASS, FAIL, SKIPPED, ERROR, INFRASTRUCTURE_UNAVAILABLE, CONFIGURATION_ERROR.
"""

import logging
from typing import Dict, Type, List, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EvaluatorResult(BaseModel):
    evaluator_name: str
    category: str  # "deterministic" or "llm"
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: str = "PASS"  # "PASS", "FAIL", "SKIPPED", "ERROR", "INFRASTRUCTURE_UNAVAILABLE", "CONFIGURATION_ERROR"
    passed: bool = True
    reason: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    feedback_key: str = ""


class EvaluatorRegistry:
    """Central registry discovering and managing registered evaluation modules."""

    def __init__(self):
        self._evaluators: Dict[str, Type[Any]] = {}

    def register(self, name: str, evaluator_cls: Type[Any]) -> Type[Any]:
        """Registers an evaluator class under a unique name."""
        if name in self._evaluators:
            logger.warning(f"[EvaluatorRegistry] Overwriting registered evaluator: '{name}'")
        self._evaluators[name] = evaluator_cls
        logger.info(f"[EvaluatorRegistry] Registered evaluator: '{name}'")
        return evaluator_cls

    def get_evaluator(self, name: str) -> Optional[Type[Any]]:
        return self._evaluators.get(name)

    def list_evaluators(self, category: Optional[str] = None) -> List[str]:
        """Lists registered evaluators, optionally filtered by category."""
        if not category:
            return list(self._evaluators.keys())
        results = []
        for name, cls in self._evaluators.items():
            if getattr(cls, "category", "").lower() == category.lower():
                results.append(name)
        return results

    def instantiate_all(self, config: Any) -> Dict[str, Any]:
        """Instantiates all registered evaluators with EvaluationConfig."""
        instances = {}
        for name, cls in self._evaluators.items():
            try:
                instances[name] = cls(config)
            except Exception as e:
                logger.error(f"[EvaluatorRegistry] Failed to instantiate evaluator '{name}': {e}")
        return instances


evaluator_registry = EvaluatorRegistry()


def register_evaluator(name: str):
    """Decorator for registering evaluator classes."""
    def decorator(cls):
        evaluator_registry.register(name, cls)
        return cls
    return decorator
