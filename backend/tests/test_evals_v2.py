"""Unit tests for Phase 2.5 Production-Grade Evaluation Platform."""

import pytest
import asyncio
from backend.evals.config import EvaluationConfig
from backend.evals.registry import evaluator_registry
from backend.evals.normalization.airport import normalize_airport
from backend.evals.normalization.city import normalize_city
from backend.evals.normalization.dates import normalize_date
from backend.evals.normalization.pipeline import normalization_pipeline
from backend.evals.datasets.loader import dataset_loader
from backend.evals.datasets.validator import validate_dataset_schema
from backend.evals.evaluator import AIEvaluator


def test_normalization_airport():
    assert normalize_airport("Delhi") == "DEL"
    assert normalize_airport("New Delhi") == "DEL"
    assert normalize_airport("Mumbai") == "BOM"
    assert normalize_airport("JFK") == "JFK"


def test_normalization_city():
    assert normalize_city("DEL") == "Delhi"
    assert normalize_city("NYC") == "New York City"
    assert normalize_city("Bombay") == "Mumbai"


def test_normalization_date():
    assert normalize_date("2026-08-15") == "2026-08-15"
    assert normalize_date("tomorrow") is not None


def test_shared_normalization_pipeline():
    exp = {"origin": "Delhi", "destination": "Bombay", "departure_date": "2026-08-15"}
    act = {"origin": "DEL", "destination": "BOM", "departure_date": "2026-08-15"}
    passed, score, details = normalization_pipeline.compare_entities(exp, act)
    assert passed is True
    assert score == 1.0


def test_evaluator_registry():
    evals = evaluator_registry.list_evaluators()
    # The full set, not a subset: importing `AIEvaluator` imports every evaluator
    # module so it self-registers, so an evaluator that stops registering is a
    # silent reduction in what the suite measures. `forecast_accuracy` is the only
    # one whose subject is the forecast rather than the plan.
    assert set(evals) == {
        "intent_accuracy",
        "entity_accuracy",
        "tool_selection",
        "latency",
        "clarification",
        "groundedness",
        "forecast_accuracy",
    }


def test_dataset_loader_and_validator():
    records = dataset_loader.load_dataset(version="2.0.0", tier="smoke")
    assert len(records) == 6, f"smoke tier is 6 cases, loaded {len(records)}"
    valid, errors = validate_dataset_schema(records)
    assert valid is True, f"Dataset schema errors: {errors}"
    # The loader records its verdict rather than logging it and returning the
    # records anyway, which is what let a corpus with duplicate IDs produce a full
    # run and a report claiming the benchmark was valid.
    assert dataset_loader.last_schema_errors == []
    assert dataset_loader.last_source == "v2.0/golden.jsonl"


@pytest.mark.asyncio
async def test_ai_evaluator_smoke_run(tmp_path):
    # `output_directory` is redirected because this test performs a real run and the
    # run writes `report.md` and `summary.json` into a timestamped subdirectory. With
    # the default it wrote them under `backend/evals/results/`, which is tracked: 32
    # such files from a 2026-07-24 run are in the index, and every execution of this
    # test added another two to the working tree. The default is now absolute and the
    # directory is gitignored, but a test still has no business writing beside the
    # shipped code — same fix as `test_dataset_exporter_and_quality_report`.
    config = EvaluationConfig(dataset_version="2.0.0", tier="smoke",
                              output_directory=str(tmp_path / "results"))
    evaluator = AIEvaluator(config=config)
    summary = await evaluator.run_evaluation(tier="smoke")
    assert summary["total_cases"] == 6

    # The redirect is asserted, not assumed. `total_cases == 6` passes whether the
    # artifacts went to `tmp_path`, to the default directory, or nowhere at all, so on
    # its own it would not notice `output_directory` being ignored again — and it being
    # ignored in a *second* place is exactly what happened: the environment inspector
    # created and probed `default_output_directory()` regardless of the config, so the
    # tracked directory was re-created on every run no matter what a caller asked for.
    runs = sorted((tmp_path / "results").iterdir())
    assert len(runs) == 1, f"expected one timestamped run directory, got {runs}"
    assert {p.name for p in runs[0].iterdir()} == {"summary.json", "report.md"}

    # And the filesystem health row must name the directory this run used. That row is
    # what the doctor prints and the markdown report shows; while it read a module-level
    # default it reported "writable" about a directory the run never wrote to, which is
    # the assertion above passing and the health check still being wrong.
    fs_reason = summary["environment"]["filesystem"]["reason"]
    assert str(tmp_path) in fs_reason, fs_reason

    # `isinstance(summary["overall_success_rate"], float)` used to be asserted
    # here, and was satisfied by exactly the value that made the defect invisible:
    # the rate was 100.0 whenever *no* evaluator executed. The rate is now over
    # executed evaluators only and is None when there are none, so the assertion
    # is that it agrees with the counts beside it.
    executed = summary["executed_evaluators_count"]
    rate = summary["overall_success_rate"]
    if executed == 0:
        assert rate is None
        assert summary["evaluation_result"] == "FAIL", (
            "a run in which every evaluator skipped measured nothing and cannot pass")
    else:
        assert rate == pytest.approx(
            100.0 * summary["passed_evaluators_count"] / executed, abs=0.01)
    assert (summary["passed_evaluators_count"]
            + summary["failed_evaluators_count"]) == executed
