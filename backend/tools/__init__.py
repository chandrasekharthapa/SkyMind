"""Operator entry points that are not part of the served application.

`backend/scratch/` held fifty files: one-off DB probes, MCP transport captures, a
613 KB scraped-payload dump, ad-hoc `ALTER TABLE` scripts, and
`ingest_mock_data.py` — the script that wrote the synthetic corpus the audit
traced the ML results back to. All of it was tracked. It is archived at
`.archive/backend-scratch-2026-09-02.tar.gz` and gone from the tree.

Two of those fifty were not scratch at all and live here instead:

* `run_validation_dashboard.py`, which a shipped test imports
  (`test_booking_curve_pipeline.test_dashboard_rendering`), so the suite depended
  on a directory named scratch.
* the eval log directory, which `services/eval_logger.py` wrote to at runtime.
  That one moved to `backend/reports/evals/` — it is an append-only log, not code.

This package is for anything in the same category: a command a person runs, not a
module the application imports.
"""
