"""Deterministic Tool Selection Precision & Recall Evaluator."""

from typing import Dict, Any, List
from backend.evals.evaluators.base import BaseEvaluator
from backend.evals.registry import EvaluatorResult, register_evaluator


@register_evaluator("tool_selection")
class ToolSelectionEvaluator(BaseEvaluator):
    name = "tool_selection"
    category = "deterministic"
    feedback_key = "tool_precision_recall"

    def evaluate_item(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> EvaluatorResult:
        exp_tools: List[str] = expected.get("required_tools", [])
        act_tools: List[str] = actual.get("tool_calls", []) or actual.get("required_tools", [])

        exp_set = set(exp_tools)
        act_set = set(act_tools)

        if not exp_set and not act_set:
            return EvaluatorResult(
                evaluator_name=self.name, category=self.category, score=1.0, passed=True,
                details={"precision": 1.0, "recall": 1.0, "missing": [], "extra": []}, feedback_key=self.feedback_key
            )

        intersection = exp_set.intersection(act_set)
        recall = len(intersection) / float(len(exp_set)) if exp_set else 1.0
        precision = len(intersection) / float(len(act_set)) if act_set else (1.0 if not exp_set else 0.0)

        f1_score = round(2 * (precision * recall) / (precision + recall), 4) if (precision + recall) > 0 else 0.0
        passed = (recall >= 1.0) and (precision >= 0.80)

        missing = list(exp_set - act_set)
        extra = list(act_set - exp_set)

        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=f1_score,
            passed=passed,
            details={"precision": round(precision, 4), "recall": round(recall, 4), "missing": missing, "extra": extra},
            feedback_key=self.feedback_key
        )
