"""Integration Test: Full Runtime Validation.

`report_dir` points at `tmp_path` because `run_full_validation()` writes four
reports, and their defaults used to resolve to the repository root where all four
are tracked. See `backend.utils.report_paths`.
"""

import pytest

from backend.services.production_readiness import production_readiness_service


def test_full_runtime_validation_suite(tmp_path):
    master_report = production_readiness_service.run_full_validation(
        report_dir=str(tmp_path))

    assert master_report["overall_status"] in ["PASS", "WARNING", "FAIL"]
    assert "model_readiness" in master_report

    # A status is a summary of the checks; the two must agree. FAIL with nothing
    # in failed_checks, or PASS with something in it, means the rollup and its own
    # evidence were computed from different things.
    failed = master_report["failed_checks"]
    warned = master_report["warning_checks"]
    status = master_report["overall_status"]

    if status == "FAIL":
        assert failed, "FAIL with no failed_checks"
    elif status == "WARNING":
        assert not failed and warned, (failed, warned)
    else:
        assert not failed and not warned, (failed, warned)
