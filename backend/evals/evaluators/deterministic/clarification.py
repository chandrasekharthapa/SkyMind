"""Deterministic Clarification Behavior Evaluator."""

from typing import Dict, Any
from backend.evals.evaluators.base import BaseEvaluator
from backend.evals.registry import EvaluatorResult, register_evaluator


@register_evaluator("clarification")
class ClarificationEvaluator(BaseEvaluator):
    name = "clarification"
    category = "deterministic"
    feedback_key = "clarification_accuracy"

    def evaluate_item(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> EvaluatorResult:
        exp_clarify = bool(expected.get("requires_clarification", False))
        act_clarify = bool(actual.get("requires_clarification", False))

        passed = exp_clarify == act_clarify
        score = 1.0 if passed else 0.0

        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=score,
            passed=passed,
            details={"expected_clarification": exp_clarify, "actual_clarification": act_clarify},
            feedback_key=self.feedback_key
        )
