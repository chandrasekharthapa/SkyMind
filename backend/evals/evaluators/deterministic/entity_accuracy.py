"""Deterministic Entity Accuracy Evaluator using Shared Normalization Pipeline."""

from typing import Dict, Any
from backend.evals.evaluators.base import BaseEvaluator
from backend.evals.registry import EvaluatorResult, register_evaluator
from backend.evals.normalization.pipeline import normalization_pipeline


@register_evaluator("entity_accuracy")
class EntityAccuracyEvaluator(BaseEvaluator):
    name = "entity_accuracy"
    category = "deterministic"
    feedback_key = "entity_accuracy"

    def evaluate_item(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> EvaluatorResult:
        exp_entities = expected.get("entities", {})
        act_entities = actual.get("entities", {})

        passed, score, details = normalization_pipeline.compare_entities(exp_entities, act_entities)

        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=score,
            passed=passed,
            details=details,
            feedback_key=self.feedback_key
        )
