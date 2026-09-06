# SkyMind Copilot -- Evaluation Report

## Executive Summary

- **Evaluation Result**: **FAIL**
- **Environment Health**: `PARTIAL`
- **Benchmark Validity**: **`PARTIAL`**
- **Planner Status**: `FALLBACK (rule_based)`
- **LLM Evaluators**: `SKIPPED`
- **LangSmith Tracing**: `DISABLED`

## Environment & Infrastructure Health

| Component | Configured | Healthy | Mode / Status | Reason |
| :--- | :--- | :--- | :--- | :--- |
| **OpenAI** | NO | NO | `FALLBACK` | Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}} |
| **Planner Engine** | YES | YES | `FALLBACK` | rule_based planner active |
| **LangSmith** | NO | NO | `DISABLED` | DISABLED |
| **Filesystem** | YES | YES | `HEALTHY` | Results directory writable |
| **Dataset** | YES | YES | `HEALTHY` | Schema & metadata verified |
| **Network** | YES | YES | `HEALTHY` | Local host connection active |

## Evaluation Task Metrics

- **Dataset Version**: `2.0.0`
- **Evaluation Tier**: `smoke`
- **Executed Evaluators**: `5`
- **Skipped Evaluators**: `1`
- **Passed Evaluators**: `1`
- **Failed Evaluators**: `4`
- **Success Rate (Executed Only)**: **20.0%**

## Evaluator Category Breakdown

| Evaluator | Category | Status | Score | Reason |
| :--- | :--- | :--- | :--- | :--- |
| `groundedness` | `llm` | `SKIPPED` | --- | Planner fallback active; offline LLM evaluator skipped |
| `intent_accuracy` | `deterministic` | `FAIL` | `0.5` | Below target threshold |
| `entity_accuracy` | `deterministic` | `FAIL` | `0.5` | Below target threshold |
| `tool_selection` | `deterministic` | `FAIL` | `0.7778` | Below target threshold |
| `latency` | `deterministic` | `PASS` | `1.0` |  |
| `clarification` | `deterministic` | `FAIL` | `0.5` | Below target threshold |

## Infrastructure Findings

- [x] Dataset loaded and verified
- [x] Shared Normalization Pipeline executed
- [!] Planner fallback active: `Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}`
- [!] `LangSmith SDK not installed; tracing disabled.`

---
*Report generated automatically by SkyMind Evaluation Engine.*