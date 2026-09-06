"""SkyMind Evaluation Doctor CLI Diagnostic Tool.

Verifies Python environment, SDK installations, API credentials, filesystem permissions,
dataset integrity, and normalization pipeline prior to benchmark execution. Those five
checks are all of them; `docs/EVALUATION_FRAMEWORK.md` used to describe this command as
running "14+ evaluation test scenarios" and inspecting "model artifact integrity", and
it does neither.

The dataset check used to be its own second load — `dataset_loader.load_dataset(...)`
followed by `if records: print("... N smoke records verified")` — which never consulted
`dataset_loader.last_schema_errors`. It printed the word "verified" for a property it
did not read, so a corpus with duplicate IDs or a missing `expected` block passed the
doctor. Meanwhile `environment_inspector.inspect()` was already computing exactly this,
including the schema outcome, and its `health.dataset` was discarded unread. There is
now one load and one verdict, and the diagnosed version and tier are the ones
`default_config` will actually run rather than a hardcoded pair.

Exit Codes:
    0 = Healthy (Full Benchmark Ready)
    1 = Partial (Fallback active or missing optional SDKs)
    2 = Invalid (Critical configuration failure)
"""

import sys
import os
import logging
from backend.evals.config import default_config
from backend.evals.datasets.loader import dataset_loader
from backend.evals.environment import environment_inspector
from backend.evals.normalization.pipeline import normalization_pipeline

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("eval_doctor")


def run_doctor() -> int:
    """Runs comprehensive diagnostic checks across evaluation infrastructure."""
    print("=" * 60)
    print("       SkyMind Copilot -- Evaluation Platform Doctor")
    print("=" * 60)

    issues = []
    warnings = []

    # 1. Python Version Check
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        print(f" [OK] Python Version:        {py_ver}")
    else:
        print(f" [FAIL] Python Version:      {py_ver} (Requires Python >= 3.10)")
        issues.append("Python version < 3.10")

    # 2. Inspect Environment & Dependencies. Told which benchmark is about to run, so
    # its dataset verdict is about that corpus and not about a default, and which
    # directory that run will write to, so the writability row below is about the
    # directory a real run would use.
    version = default_config.dataset_version
    tier = default_config.tier
    health = environment_inspector.inspect(dataset_version=version, tier=tier,
                                           output_directory=default_config.output_directory)

    if health.langsmith.healthy:
        print(" [OK] LangSmith SDK & Key:   Active")
    else:
        print(f" [WARN] LangSmith SDK & Key: {health.langsmith.reason}")
        warnings.append(f"LangSmith: {health.langsmith.reason}")

    if health.openai.healthy:
        print(" [OK] OpenAI API Key:        Configured")
    else:
        print(f" [WARN] OpenAI API Key:      {health.openai.reason}")
        warnings.append(f"OpenAI: {health.openai.reason}")

    # 3. Filesystem Permissions. The path came from a literal here, so this line kept
    # printing "backend/evals/results" whatever directory the check had actually
    # written to. `health.filesystem.reason` now carries the resolved path, on the same
    # rule as the dataset row below: print what was checked.
    if health.filesystem.healthy:
        print(f" [OK] Filesystem Writable:   {health.filesystem.reason}")
    else:
        print(f" [FAIL] Filesystem Writable: {health.filesystem.reason}")
        issues.append("Filesystem error")

    # 4. Dataset Integrity. `health.dataset.reason` carries the record count, the file
    # it came from, and any schema error — so what is printed is what was checked.
    if health.dataset.healthy:
        print(f" [OK] Golden Dataset v{version}: {health.dataset.reason}")
    else:
        print(f" [FAIL] Golden Dataset v{version}: {health.dataset.reason}")
        issues.append(f"Dataset '{version}' tier '{tier}': {health.dataset.reason}")
        for err in dataset_loader.last_schema_errors[:5]:
            print(f"        - {err}")

    # 5. Normalization Pipeline Test
    passed, score, _ = normalization_pipeline.compare_entities({"origin": "Delhi"}, {"origin": "DEL"})
    if passed and score == 1.0:
        print(" [OK] Normalization Pipeline: Active (DEL == Delhi verified)")
    else:
        print(" [FAIL] Normalization Pipeline: Entity resolution error")
        issues.append("Normalization pipeline failed")

    print("-" * 60)
    print(f" Benchmark validity for tier '{tier}': {health.benchmark_validity}")

    if issues:
        print(" DIAGNOSTIC RESULT: INVALID (Critical environment issues detected)")
        for issue in issues:
            print(f"  - {issue}")
        print(" Exit Code: 2")
        return 2

    if warnings:
        print(" DIAGNOSTIC RESULT: PARTIAL (Environment operational with fallback mode)")
        for warn in warnings:
            print(f"  - {warn}")
        print(" Exit Code: 1")
        return 1

    # Says what was checked. The previous wording — "Platform 100% operational for Full
    # Benchmarks" — asserted a percentage nothing measured and named a tier this command
    # never loads.
    print(f" DIAGNOSTIC RESULT: HEALTHY (all 5 checks passed for tier '{tier}')")
    print(" Exit Code: 0")
    return 0


if __name__ == "__main__":
    sys.exit(run_doctor())
