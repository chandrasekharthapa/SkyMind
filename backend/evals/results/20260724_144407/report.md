# SkyMind Copilot — Evaluation Report

**Dataset Version**: `2.0.0`  
**Evaluation Tier**: `smoke`  
**Git SHA**: `local_development`  
**Config Hash**: `a3c7cb7d91`  

## Overall Task Metrics

| Metric | Value |
| :--- | :--- |
| **Total Cases Evaluated** | 6 |
| **Passed Cases** | 3 |
| **Overall Success Rate** | **50.0%** |
| **Intent Accuracy** | 50.0% |
| **Entity Accuracy** | 50.0% |
| **Tool Precision / Recall** | 0.7778 |
| **P95 Latency** | 3444.6 ms |

## Evaluator Category Breakdown

| Evaluator Name | Category | Score | Passed |
| :--- | :--- | :--- | :--- |
| `intent_accuracy` | `deterministic` | `0.5` | ❌ FAIL |
| `entity_accuracy` | `deterministic` | `0.5` | ❌ FAIL |
| `tool_selection` | `deterministic` | `0.7778` | ❌ FAIL |
| `latency` | `deterministic` | `1.0` | ✅ PASS |
| `clarification` | `deterministic` | `0.5` | ❌ FAIL |
| `groundedness` | `llm` | `0.0` | ❌ FAIL |

---
*Report generated automatically by SkyMind Evaluation Engine.*