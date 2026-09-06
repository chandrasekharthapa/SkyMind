# SkyMind Copilot -- Evaluation Report

## Environment

- **Dataset Version**: `2.0.0`
- **Evaluation Tier**: `smoke`
- **Planner Provider**: `HEALTHY`
- **Evaluator Provider**: `HEALTHY`
- **LangSmith Status**: `MISSING_PACKAGE`

## Infrastructure Status

- **Planner**: `FALLBACK (rule_based)`
- **Judge**: `ACTIVE`
- **OpenAI Quota**: `CONFIGURED`

## Evaluation Summary

- **Executed Evaluators**: `6`
- **Skipped Evaluators**: `0`
- **Passed Evaluators**: `1`
- **Failed Evaluators**: `5`
- **Success Rate (Executed Only)**: **16.67%**

## Evaluator Category Breakdown

| Evaluator | Category | Status | Score | Reason |
| :--- | :--- | :--- | :--- | :--- |
| `intent_accuracy` | `deterministic` | `FAIL` | `0.5` | Below target threshold |
| `entity_accuracy` | `deterministic` | `FAIL` | `0.5` | Below target threshold |
| `tool_selection` | `deterministic` | `FAIL` | `0.7778` | Below target threshold |
| `latency` | `deterministic` | `PASS` | `0.5` |  |
| `clarification` | `deterministic` | `FAIL` | `0.5` | Below target threshold |
| `groundedness` | `llm` | `PASS` | `1.0` | Executed normally |

## Infrastructure Findings

- [x] Dataset loaded and verified
- [x] Shared Normalization Pipeline executed
- [!] Planner fallback active: `Quota limit or network timeout`
- [!] `LangSmith SDK not installed; tracing disabled.`

---
*Report generated automatically by SkyMind Evaluation Engine.*