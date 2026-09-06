"""SkyMind Automated AI Evaluation Engine (Lightweight Coordinator).

Orchestrates versioned dataset loading, execution runners, self-registered evaluators,
environment health inspection, benchmark validity determination, and local result snapshots.

The coordinator's own honesty is the thing to preserve when editing this file. Two
properties are load-bearing and both were previously violated here:

* A run that measured nothing must not report a pass. `overall_success_rate` was
  `100.0` whenever `executed_count` was zero, and `failed_count` is zero in that
  state too, so every-evaluator-skipped was byte-identical to every-evaluator-passed.
  The rate is `None` when nothing executed and the verdict is `FAIL`.
* A headline metric must have no optimistic default. `intent_accuracy` and
  `entity_accuracy` defaulted to 100.0, `tool_f1_score` to 1.0 and `p95_latency_ms`
  to 50.0 when an evaluator was absent or had returned `score=None` — which is
  exactly what a skipped evaluator returns. They are `None` now, and the markdown
  report renders that as "---" rather than as a number.

`benchmark_validity` is the inspector's verdict, not a recomputation: `INVALID` means
the dataset did not load or its schema did not hold, and this file must not soften it.
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.evals.config import EvaluationConfig, default_config
from backend.evals.registry import evaluator_registry
from backend.evals.datasets.loader import dataset_loader
from backend.evals.environment import environment_inspector
from backend.evals.runners.planner_runner import planner_runner
from backend.evals.runners.judge_runner import judge_runner
from backend.evals.reports.markdown import generate_markdown_report
from backend.evals.reports.json import generate_json_report
from backend.services.langsmith_tracer import langsmith_tracer

# Ensure all evaluators self-register
import backend.evals.evaluators.deterministic.intent_accuracy
import backend.evals.evaluators.deterministic.entity_accuracy
import backend.evals.evaluators.deterministic.tool_selection
import backend.evals.evaluators.deterministic.latency
import backend.evals.evaluators.deterministic.clarification
import backend.evals.evaluators.deterministic.groundedness
# The one evaluator whose subject is the forecast rather than the plan. It ignores
# the planner items and reads resolved forecasts out of the store, so the suite's
# headline number stops being a statement about query parsing alone.
import backend.evals.evaluators.deterministic.forecast_accuracy

logger = logging.getLogger(__name__)


class AIEvaluator:
    """Lightweight Evaluation Coordinator."""

    def __init__(self, config: Optional[EvaluationConfig] = None):
        self.config = config or default_config

    async def run_evaluation(self, tier: Optional[str] = None) -> Dict[str, Any]:
        """Runs evaluation suite across target dataset tier with environment & validity awareness."""
        target_tier = tier or self.config.tier
        t_start = time.perf_counter()

        # 1. Environment & Provider Health Inspection. The inspector is told which
        # dataset the run is about so that its Dataset check is a check of the
        # benchmark actually under evaluation, and which directory this run will
        # write to so that its filesystem check probes that directory rather than
        # creating the default one beside the shipped code.
        prov_health = environment_inspector.inspect(
            dataset_version=self.config.dataset_version, tier=target_tier,
            output_directory=self.config.output_directory)

        logger.info(f"[AIEvaluator] Starting evaluation run. Tier: '{target_tier}' | Version: '{self.config.dataset_version}'")
        test_cases = dataset_loader.load_dataset(version=self.config.dataset_version, tier=target_tier)
        dataset_schema_errors = list(dataset_loader.last_schema_errors)

        if not test_cases:
            logger.warning(f"[AIEvaluator] No test cases found for tier '{target_tier}'.")
            # Carries the health report and the schema errors so the markdown report
            # and the CLI exit code have something to say beyond "empty".
            return {
                "status": "empty",
                "evaluation_result": "FAIL",
                "benchmark_validity": "INVALID",
                "dataset_version": self.config.dataset_version,
                "tier": target_tier,
                "total_cases": 0,
                "executed_evaluators_count": 0,
                "skipped_evaluators_count": 0,
                "passed_evaluators_count": 0,
                "failed_evaluators_count": 0,
                "overall_success_rate": None,
                "environment": prov_health.model_dump(),
                "provider_health": prov_health.model_dump(),
                "evaluator_results": {},
                "dataset_schema_errors": dataset_schema_errors,
                "warnings": prov_health.warnings,
            }

        # 2. Execute Test Cases & Track Planner Provenance
        evaluation_items = []
        planner_sources = []
        fallback_reasons = []

        for tc in test_cases:
            expected = tc.get("expected", {})
            actual_plan = await planner_runner.run_single(tc)

            planner_sources.append(actual_plan.get("planner_source", "hybrid"))
            if actual_plan.get("fallback_used"):
                err = actual_plan.get("planner_reason", "Quota limit or network timeout")
                fallback_reasons.append(err)

            evaluation_items.append({
                "id": tc.get("id"),
                "category": tc.get("category"),
                "expected": expected,
                "actual": actual_plan
            })

        # Determine overall Planner Provenance
        planner_fallback_used = any("rule_based" in src for src in planner_sources)
        planner_provenance = {
            "planner_status": "FALLBACK" if planner_fallback_used else "PRIMARY",
            "planner_source": "rule_based" if planner_fallback_used else "hybrid",
            "planner_model": "rule_based_engine_v1" if planner_fallback_used else "meta/llama-3.1-70b-instruct",
            "planner_version": "1.1.0",
            "fallback_used": planner_fallback_used,
            "planner_reason": fallback_reasons[0] if fallback_reasons else "Executed primary planner"
        }

        # Determine Benchmark Validity. The inspector's own verdict is respected
        # rather than recomputed: it is the thing that knows whether the dataset
        # loaded, and INVALID must not be softened to PARTIAL here.
        if prov_health.benchmark_validity == "INVALID" or dataset_schema_errors:
            benchmark_validity = "INVALID"
        elif planner_fallback_used or prov_health.overall_health != "HEALTHY":
            benchmark_validity = "PARTIAL"
        else:
            benchmark_validity = "FULL"

        # 3. Execute Self-Registered Evaluators
        evaluator_instances = evaluator_registry.instantiate_all(self.config)
        evaluator_results = {}

        executed_count = 0
        skipped_count = 0
        passed_count = 0
        failed_count = 0

        for name, inst in evaluator_instances.items():
            res = inst.evaluate_batch(evaluation_items)
            evaluator_results[name] = res.model_dump()

            # `INFRASTRUCTURE_UNAVAILABLE` is a skip too. Testing only for
            # "SKIPPED" counted it as executed and then, because such a result
            # carried `passed=True`, as a pass.
            if res.status in ("SKIPPED", "INFRASTRUCTURE_UNAVAILABLE"):
                skipped_count += 1
            else:
                executed_count += 1
                if res.passed:
                    passed_count += 1
                else:
                    failed_count += 1

            # Push Feedback to LangSmith if active
            if langsmith_tracer.client and res.feedback_key and res.score is not None:
                try:
                    langsmith_tracer.client.create_feedback(
                        run_id=None,
                        key=res.feedback_key,
                        score=res.score,
                        comment=f"Evaluator '{name}' score: {res.score}"
                    )
                except Exception as e:
                    logger.debug(f"LangSmith feedback push optional notice: {e}")

        # Executed-only success rate, and None when nothing executed. The old
        # expression ended `else 100.0`, so a run in which every evaluator skipped —
        # no API key, planner in fallback, an evaluator that failed to construct —
        # published a 100% success rate; and since `failed_count` is zero in that
        # state too, the verdict came out PASS. No number honestly summarises zero
        # measurements, so the field is None and the verdict below is FAIL.
        success_rate = (round((passed_count / float(executed_count)) * 100.0, 2)
                        if executed_count > 0 else None)
        total_time = round(time.perf_counter() - t_start, 3)

        if executed_count == 0:
            # Logged rather than left implicit: the reasons are the only account of
            # why the suite measured nothing, and they are what distinguishes a
            # missing credential from a broken evaluator.
            skip_reasons = {n: (r or {}).get("reason") for n, r in evaluator_results.items()}
            logger.error(f"[AIEvaluator] No evaluator executed; run cannot pass. "
                         f"Skip reasons: {skip_reasons}")
            eval_result = "FAIL"
        elif benchmark_validity == "INVALID":
            # A benchmark whose own dataset did not hold cannot certify anything,
            # however well the evaluators that did run scored.
            eval_result = "FAIL"
        elif failed_count == 0:
            eval_result = "PASS" if benchmark_validity == "FULL" else "PARTIAL"
        else:
            eval_result = "FAIL"

        def _score_pct(name: str) -> Optional[float]:
            """An evaluator's score as a percentage, or None if it has none.

            The default used to be 1.0, so an evaluator missing from the registry, or
            one that skipped and returned `score=None`, published 100.0. None is the
            only honest value for a metric nothing measured, and the markdown
            report renders it as "---".
            """
            score = (evaluator_results.get(name) or {}).get("score")
            return None if score is None else round(float(score) * 100.0, 2)

        def _score_raw(name: str) -> Optional[float]:
            score = (evaluator_results.get(name) or {}).get("score")
            return None if score is None else float(score)

        summary = {
            "dataset_version": self.config.dataset_version,
            "evaluation_version": self.config.evaluation_version,
            "tier": target_tier,
            "git_sha": self.config.git_sha,
            "config_hash": self.config.config_hash,
            "evaluation_result": eval_result,
            "benchmark_validity": benchmark_validity,
            "environment": prov_health.model_dump(),
            "provider_health": prov_health.model_dump(),
            "infrastructure": {
                "planner_mode": planner_provenance["planner_status"],
                "openai_mode": "FALLBACK" if planner_fallback_used else "PRIMARY",
                "judge_status": "ACTIVE" if prov_health.openai.configured else "SKIPPED"
            },
            "planner": planner_provenance,
            "planner_provenance": planner_provenance,
            "total_cases": len(test_cases),
            "executed_evaluators_count": executed_count,
            "skipped_evaluators_count": skipped_count,
            "passed_evaluators_count": passed_count,
            "failed_evaluators_count": failed_count,
            "overall_success_rate": success_rate,
            "intent_accuracy": _score_pct("intent_accuracy"),
            "entity_accuracy": _score_pct("entity_accuracy"),
            "tool_f1_score": _score_raw("tool_selection"),
            # No default either: 50.0 was a plausible-looking latency for a run in
            # which the latency evaluator had not measured one.
            "p95_latency_ms": (evaluator_results.get("latency") or {})
                              .get("details", {}).get("p95_ms"),
            "total_evaluation_time_seconds": total_time,
            "evaluator_results": evaluator_results,
            "dataset_schema_errors": dataset_schema_errors,
            "warnings": prov_health.warnings
        }

        # 4. Save Local Artifact Snapshot
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(self.config.output_directory, timestamp_str)
        os.makedirs(out_dir, exist_ok=True)

        json_text = generate_json_report(summary)
        md_text = generate_markdown_report(summary)

        with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
            f.write(json_text)
        with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
            f.write(md_text)

        logger.info(f"[AIEvaluator] Finished evaluation run in {total_time}s. Artifacts saved to '{out_dir}'. Result: {eval_result} | Validity: {benchmark_validity}")
        return summary


evaluator = AIEvaluator()
