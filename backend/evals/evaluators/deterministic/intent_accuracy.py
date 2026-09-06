"""Deterministic Intent Accuracy Evaluator for SkyMind Evaluation Platform."""

from typing import Dict, Any
from backend.evals.evaluators.base import BaseEvaluator
from backend.evals.registry import EvaluatorResult, register_evaluator


@register_evaluator("intent_accuracy")
class IntentAccuracyEvaluator(BaseEvaluator):
    name = "intent_accuracy"
    category = "deterministic"
    feedback_key = "intent_accuracy"

    def evaluate_item(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> EvaluatorResult:
        exp_intent = str(expected.get("intent", "")).upper()
        act_intent = str(actual.get("intent", "")).upper()

        passed = (exp_intent == act_intent) or (exp_intent in ["GENERAL_INQUIRY", "SEARCH_FLIGHTS"] and act_intent in ["GENERAL_INQUIRY", "SEARCH_FLIGHTS"])
        score = 1.0 if passed else 0.0

        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=score,
            passed=passed,
            details={"expected": exp_intent, "actual": act_intent},
            feedback_key=self.feedback_key
        )
