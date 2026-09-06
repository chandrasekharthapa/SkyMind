# SkyMind Copilot Evaluation Platform

## Overview
Version-controlled golden datasets in Git, a shared entity-normalization pipeline, self-registering evaluators, honest-by-construction reporting, and optional LangSmith tracing.

## Design Philosophy
1. **Git as canonical dataset repository**: versioned JSONL corpora live in Git at `datasets/v<major>.<minor>/golden.jsonl`. The requested version selects the directory, and the `metadata.json` beside the corpus is cross-checked against it on every load — a declared record count or version the corpus contradicts is a schema error, and a schema error invalidates the run. There is one published corpus, `datasets/v2.0/`; `benchmark_dataset_v1.json` is the converted legacy corpus and is served only for a 1.x request.
2. **A result must be able to fail**: an evaluator that skipped is not an evaluator that passed, `overall_success_rate` is `None` rather than 100.0 when nothing executed, a run in which every evaluator skipped is `FAIL`, and a run over a corpus that failed its own schema validation is `INVALID` and cannot report `PASS`.
3. **LangSmith is optional**: when the `langsmith` SDK and an API key are present, runs are traced and evaluator scores are pushed as feedback on a best-effort basis (failures are logged at debug and do not affect the verdict). It is not a system of record — the artifacts written under `results/<timestamp>/` are. Synchronising the Git corpus to the LangSmith Datasets API happens only via `python -m backend.evals.sync`, which no-ops without a client.

## Quick Start CLI Commands
```bash
# Diagnose the environment: 5 checks, exit 0 healthy / 1 partial / 2 critical
python -m backend.evals.doctor

# Smoke tier — 6 cases
python -m backend.evals.run --tier smoke

# Full benchmark — all 15 cases
python -m backend.evals.run --tier full

# Sync the Git JSONL corpus to LangSmith Datasets (requires the SDK and a key)
python -m backend.evals.sync

# Compare two run artifacts, by path to their summary.json
python -m backend.evals.compare --baseline results/<ts>/summary.json --target results/<ts>/summary.json
```

`--tier nightly` and `--tier regression` are accepted by the CLI but match **zero** records: no golden record carries either tag, so both load nothing and the run reports `FAIL` / `INVALID`. Adversarial cases are marked with the per-record boolean `regression` (2 of 15), not with a tier.

## Shared Normalization Pipeline
Entity comparisons run through `SharedNormalizationPipeline`, which rewrites four field families and passes every other key through unchanged:
1. `origin` / `from` and `destination` / `to` → both an IATA code and a city name (`DEL` == `Delhi` == `New Delhi`, `NYC` == `New York City`)
2. `departure_date` / `date` → canonical `YYYY-MM-DD` (`tomorrow` resolves against today)
3. `cabin` / `cabin_class` → upper case
4. Any other key is compared case-insensitively as-is

An `airline` entity is therefore compared literally: `6E` and `IndiGo` do not match here. `normalization/airline.py` resolves that pair, but it is used by the groundedness evaluator, not by this pipeline.

## Evaluators
All seven are deterministic and live in `evaluators/deterministic/`. There is no `evaluators/llm/` directory and no LLM-judged evaluator; the earlier list here named four (Groundedness, Faithfulness, Correctness, Hallucination Review) of which only groundedness exists, as a deterministic check. It also named a Cost/Tokens evaluator, which does not exist.

| Evaluator | What it scores |
| :--- | :--- |
| `intent_accuracy` | Predicted intent against the golden intent |
| `entity_accuracy` | Extracted entities, compared after normalization |
| `tool_selection` | Precision, recall and F1 over the required tool set; bound is recall == 1.0 and precision >= 0.80 |
| `latency` | P50/P90/P95/P99 of planner latency; bound is P95 <= 3500 ms |
| `clarification` | Whether the planner's `requires_clarification` decision matched the golden decision |
| `groundedness` | Whether entities in the answer are supported by the retrieved context |
| `forecast_accuracy` | The error of forecasts this system published and later resolved |

`forecast_accuracy` is the only evaluator whose subject is a forecast rather than a plan. It ignores the planner items, reads resolved forecasts out of `forecast_store`, and bounds R² (must beat a constant chosen with hindsight), MAPE (ceiling 15%), and — once a quoted fare is recorded on the forecast row — the improvement over the fare already on screen. Without database credentials it reports `INFRASTRUCTURE_UNAVAILABLE`, and below 30 resolved forecasts it reports `SKIPPED`. Until it executes, `overall_success_rate` is a statement about query planning only.
