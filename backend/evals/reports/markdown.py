"""Markdown Summary Report Generator for SkyMind Evaluation Platform (Phase 2.5.3).

Exposes Evaluation Result, Environment Health, Benchmark Validity, and Detailed
Infrastructure Table.

Everything this file used to state without consulting its argument:

  * Three rows of the infrastructure table — **Filesystem**, **Dataset** and
    **Network** — were literal `| YES | YES | \\`HEALTHY\\` |` text. They rendered
    "Results directory writable", "Schema & metadata verified" and "Local host
    connection active" for a run in which the results directory was read-only, the
    dataset had failed to load, and nothing had checked the network at all. The
    inspector reports on the first two; the third was never measured by anything,
    so the row is gone rather than given a fabricated source.
  * Two checklist items, "Dataset loaded and verified" and "Shared Normalization
    Pipeline executed", were unconditional `- [x]`.
  * `evaluation_result` defaulted to `PASS`, `benchmark_validity` to `FULL`,
    `overall_health` to `HEALTHY` and the planner to `PRIMARY`, so
    `generate_markdown_report({})` produced a clean passing report. A summary that
    does not carry a verdict now renders `UNKNOWN`, which is the true statement.

And one defect in the other direction, which is why the first three went unnoticed
for as long as they did. The OpenAI and LangSmith rows read four flat keys —
`openai_api_key_configured`, `openai_quota_status`, `langsmith_installed`,
`langsmith_api_key_configured` — that **no summary has ever contained**.
`summary["environment"]` is a `ProviderHealthReport.model_dump()`, whose keys are
`overall_health`, `benchmark_validity`, `openai`, `langsmith`, `filesystem`,
`dataset` and `warnings`; the per-service state lives one level down. So every
`.get()` returned `None`, "LLM Evaluators" read `SKIPPED` and "LangSmith Tracing"
read `DISABLED` on every run regardless of what was configured, and the OpenAI row
was always `NO | NO`. The two tests covering this function each hand-built a
flat-key `environment` dict, so they exercised a shape the production code does not
emit — which is the reason a table wired to nothing looked tested. The reads now
follow the real dump and the fixtures were corrected to match it.
"""

from typing import Any, Dict, Optional


def _yes_no(value: Optional[bool]) -> str:
    """YES / NO / `?` — the third for a health field the inspector did not set."""
    if value is None:
        return "?"
    return "YES" if value else "NO"


def _component_row(label: str, component: Dict[str, Any]) -> str:
    """One infrastructure row, read from the inspector's report for that component."""
    return (f"| **{label}** | {_yes_no(component.get('configured'))} "
            f"| {_yes_no(component.get('healthy'))} "
            f"| `{component.get('current_mode') or 'UNKNOWN'}` "
            f"| {component.get('reason') or 'N/A'} |")


def generate_markdown_report(summary: Dict[str, Any]) -> str:
    """Generates structured GitHub-flavored Markdown evaluation summary report."""
    # `environment` and `provider_health` are the same `ProviderHealthReport` dump;
    # either key is accepted, and the per-service state is read from inside it.
    prov = summary.get("provider_health") or summary.get("environment") or {}
    openai_h = prov.get("openai", {}) or {}
    langsmith_h = prov.get("langsmith", {}) or {}
    filesystem_h = prov.get("filesystem", {}) or {}
    dataset_h = prov.get("dataset", {}) or {}
    planner_info = summary.get("planner_provenance", {}) or summary.get("planner", {}) or {}

    # No optimistic defaults: an absent verdict is unknown, not a pass.
    eval_result = summary.get("evaluation_result") or "UNKNOWN"
    env_health = prov.get("overall_health") or "UNKNOWN"
    validity = summary.get("benchmark_validity") or "UNKNOWN"
    planner_status = planner_info.get("planner_status") or "UNKNOWN"
    llm_status = "ACTIVE" if openai_h.get("configured") else "SKIPPED"
    ls_status = langsmith_h.get("current_mode") or "UNKNOWN"

    success_rate = summary.get("overall_success_rate")
    success_str = "n/a (no evaluator executed)" if success_rate is None else f"**{success_rate}%**"

    md = [
        "# SkyMind Copilot -- Evaluation Report",
        "",
        "## Executive Summary",
        "",
        f"- **Evaluation Result**: **{eval_result}**",
        f"- **Environment Health**: `{env_health}`",
        f"- **Benchmark Validity**: **`{validity}`**",
        f"- **Planner Status**: `{planner_status} ({planner_info.get('planner_source', 'unknown')})`",
        f"- **LLM Evaluators**: `{llm_status}`",
        f"- **LangSmith Tracing**: `{ls_status}`",
        "",
        "## Environment & Infrastructure Health",
        "",
        "| Component | Configured | Healthy | Mode / Status | Reason |",
        "| :--- | :--- | :--- | :--- | :--- |",
        # Every row below is read from the inspector's report for that component.
        # None is asserted by this file, and a component the inspector did not set
        # renders `?` rather than a guess.
        _component_row("OpenAI", openai_h),
        (f"| **Planner Engine** | YES | {_yes_no(planner_status == 'PRIMARY')} "
         f"| `{planner_status}` "
         f"| {planner_info.get('planner_reason') or 'no planner reason recorded'} |"),
        _component_row("LangSmith", langsmith_h),
        _component_row("Filesystem", filesystem_h),
        _component_row("Dataset", dataset_h),
        "",
        "## Evaluation Task Metrics",
        "",
        f"- **Dataset Version**: `{summary.get('dataset_version', 'unknown')}`",
        f"- **Evaluation Tier**: `{summary.get('tier', 'unknown')}`",
        f"- **Total Test Cases**: `{summary.get('total_cases', 0)}`",
        f"- **Executed Evaluators**: `{summary.get('executed_evaluators_count', 0)}`",
        f"- **Skipped Evaluators**: `{summary.get('skipped_evaluators_count', 0)}`",
        f"- **Passed Evaluators**: `{summary.get('passed_evaluators_count', 0)}`",
        f"- **Failed Evaluators**: `{summary.get('failed_evaluators_count', 0)}`",
        f"- **Success Rate (Executed Only)**: {success_str}",
        "",
        "## Evaluator Category Breakdown",
        "",
        "| Evaluator | Category | Status | Score | Reason |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]

    eval_results = summary.get("evaluator_results", {})
    for name, res in eval_results.items():
        score_val = res.get("score")
        score_str = f"`{score_val}`" if score_val is not None else "---"
        status_str = f"`{res.get('status', 'UNKNOWN')}`"
        cat = res.get("category", "deterministic")
        reason = res.get("reason") or "no reason recorded"
        md.append(f"| `{name}` | `{cat}` | {status_str} | {score_str} | {reason} |")

    if not eval_results:
        md.append("| _none_ | --- | `NOT_RUN` | --- | no evaluator produced a result |")

    # Infrastructure findings, each from the report rather than from this file.
    warnings = summary.get("warnings", []) or []
    dataset_healthy = dataset_h.get("healthy")
    md.extend([
        "",
        "## Infrastructure Findings",
        "",
        f"- [{'x' if dataset_healthy else ' '}] Dataset loaded and verified"
        + ("" if dataset_healthy else f" — {dataset_h.get('reason') or 'not verified'}"),
    ])

    if planner_status == "FALLBACK":
        md.append(f"- [!] Planner fallback active: `{planner_info.get('planner_reason', 'planner reason not recorded')}`")
    elif planner_status == "PRIMARY":
        md.append("- [x] Primary planner active")
    else:
        md.append("- [ ] Planner status not recorded")

    if warnings:
        for w in warnings:
            md.append(f"- [!] `{w}`")
    else:
        md.append("- [x] No infrastructure warning recorded")

    md.extend([
        "",
        "---",
        "*Report generated automatically by SkyMind Evaluation Engine.*"
    ])

    return "\n".join(md)
