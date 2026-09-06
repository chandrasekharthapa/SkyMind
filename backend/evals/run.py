"""CLI Evaluation Suite Entry Point for SkyMind Platform.

Usage:
    python -m backend.evals.run --tier smoke
    python -m backend.evals.run --tier full
    python -m backend.evals.run --tier nightly
    python -m backend.evals.run --tier regression

Exit codes:
    0 = PASS      every executed evaluator passed on a fully valid benchmark
    1 = FAIL      at least one evaluator failed, or the suite executed nothing
    2 = PARTIAL   every executed evaluator passed, but the benchmark was degraded
                  (planner fallback, or a provider the run depended on unhealthy)

This used to end in `sys.exit(0)`, unconditionally, one line after the branch that
logs a fallback warning. A CI step running this command therefore went green on a
`FAIL` summary, on a run that loaded zero test cases, and on a run whose planner
had fallen back to the rule-based engine — which is to say the evaluation suite
could not report a failure through the only channel CI reads. `PARTIAL` gets its
own code rather than being folded into either: a degraded run is not a passing run,
but it is also not evidence of a regression, and a caller that wants to tolerate
one can test for 2 specifically.
"""

import sys
import argparse
import asyncio
import logging
from backend.evals.config import EvaluationConfig
from backend.evals.evaluator import AIEvaluator
from backend.evals.reports.markdown import generate_markdown_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_PARTIAL = 2


def exit_code_for(summary: dict) -> int:
    """The process status implied by an evaluation summary.

    Separate from `main` so it is testable without running a suite, and so the
    mapping from verdict to status lives in one place.
    """
    result = str(summary.get("evaluation_result", "")).upper()
    if result == "PASS":
        return EXIT_PASS
    if result == "PARTIAL":
        return EXIT_PARTIAL
    # Anything else — "FAIL", the "empty" summary returned when the tier loaded no
    # test cases, or a summary with no verdict at all — is a failure. Defaulting to
    # PASS here would reintroduce exactly the bug this function replaces.
    return EXIT_FAIL


def main():
    parser = argparse.ArgumentParser(description="SkyMind Copilot Evaluation Platform CLI")
    parser.add_argument("--tier", choices=["smoke", "full", "nightly", "regression"], default="smoke", help="Evaluation dataset tier")
    parser.add_argument("--version", default="2.0.0", help="Dataset version")
    parser.add_argument("--dry-run", action="store_true", help="Dry run evaluation")
    args = parser.parse_args()

    config = EvaluationConfig(dataset_version=args.version, tier=args.tier)
    evaluator = AIEvaluator(config=config)

    logger.info(f"Running evaluation benchmark (Tier: {args.tier}, Version: {args.version})...")
    summary = asyncio.run(evaluator.run_evaluation(tier=args.tier))

    md_report = generate_markdown_report(summary)
    print("\n" + md_report + "\n")

    planner_status = summary.get("planner", {}).get("planner_status")
    if planner_status == "FALLBACK":
        logger.warning(f"Evaluation completed using FALLBACK planner ({summary.get('planner', {}).get('planner_reason')}). Infrastructure warning logged.")

    code = exit_code_for(summary)
    logger.log(
        logging.INFO if code == EXIT_PASS else logging.ERROR,
        "Evaluation result: %s | validity: %s | executed: %s, passed: %s, failed: %s "
        "| exit %d",
        summary.get("evaluation_result"), summary.get("benchmark_validity"),
        summary.get("executed_evaluators_count"),
        summary.get("passed_evaluators_count"),
        summary.get("failed_evaluators_count"), code,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
