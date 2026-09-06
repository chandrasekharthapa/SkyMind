"""Unit Tests for SkyMind AI Evaluation Engine — collection-safe version.

Tests the AIEvaluator coordinator structure and ensure its public API is intact.
These tests do NOT execute live network calls or call the async runner; they verify
the structural contract of the evaluator module only.
"""

import pytest
from backend.evals.evaluator import AIEvaluator


def test_ai_evaluator_instantiates():
    """Verify AIEvaluator can be imported and instantiated without errors."""
    evaluator = AIEvaluator()
    assert evaluator is not None
    assert hasattr(evaluator, "config")
    assert hasattr(evaluator, "run_evaluation")


def test_ai_evaluator_config_defaults():
    """Verify default config is populated with expected field types."""
    evaluator = AIEvaluator()
    cfg = evaluator.config
    assert isinstance(cfg.dataset_version, str) and len(cfg.dataset_version) > 0
    assert isinstance(cfg.evaluation_version, str) and len(cfg.evaluation_version) > 0
    assert isinstance(cfg.tier, str) and len(cfg.tier) > 0


def test_ai_evaluator_run_evaluation_is_async():
    """Verify run_evaluation is an async coroutine function."""
    import inspect
    evaluator = AIEvaluator()
    assert inspect.iscoroutinefunction(evaluator.run_evaluation), (
        "AIEvaluator.run_evaluation must be an async coroutine function"
    )
