"""Test Suite for Production Readiness Master Service."""

import json
import os

import pytest

from backend.services.production_readiness import production_readiness_service

# Every report `run_full_validation` is responsible for, its own last.
EXPECTED_REPORTS = [
    "historical_data_report.json",
    "feature_validation_report.json",
    "drift_report.json",
    "production_readiness_report.json",
]


def test_production_readiness_run(tmp_path):
    """The rollup names every subsystem, and writes where it was told to.

    The disk assertion here used to be

        report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "..", "production_readiness_report.json")
        assert os.path.exists(report_file)

    which is a check that cannot fail for its stated reason: that path is a
    tracked file, so it exists before the test starts and would still exist if
    `run_full_validation` wrote nothing at all. Worse, it *did* pass because the
    run wrote there — four tracked reports were being rewritten by the test suite.
    Pointing the run at `tmp_path` makes the existence assertion meaningful and
    stops the suite from editing the working tree.
    """
    report = production_readiness_service.run_full_validation(report_dir=str(tmp_path))

    assert "overall_status" in report
    assert report["overall_status"] in ["PASS", "WARNING", "FAIL"]
    assert "historical_data_audit" in report
    assert "feature_validation" in report
    assert "model_readiness" in report
    assert "drift_detection" in report
    assert "prediction_validation" in report
    assert "recommendation_validation" in report

    written = report.get("report_written_to")
    assert written == os.path.join(str(tmp_path), "production_readiness_report.json"), (
        f"write outcome: {report.get('report_write_error') or written}")
    with open(written) as fh:
        assert json.load(fh) == report


def test_no_report_lands_outside_the_directory_it_was_given(tmp_path):
    """A subsystem that ignores the destination is the regression to catch.

    Each sub-service takes its own `destination`, and the rollup derives all four
    from one directory. If any of them falls back to its module-level default, the
    file appears under `backend/reports/` instead of here — and before that
    default was moved, under the repository root.
    """
    production_readiness_service.run_full_validation(report_dir=str(tmp_path))

    landed = sorted(os.listdir(str(tmp_path)))
    missing = [name for name in EXPECTED_REPORTS if name not in landed]
    assert not missing, f"not written to the directory given: {missing} (found {landed})"


def test_a_failed_check_is_quoted_from_the_subsystem_that_failed(tmp_path):
    """Rollup messages must carry the subsystem's own reason.

    The data-audit line appended the fixed string "Historical Data Audit: Partial
    coverage or duplicate observations" for any non-PASS status — including the
    empty-database path, whose actual reason is "Database returned no records".
    """
    report = production_readiness_service.run_full_validation(report_dir=str(tmp_path))

    audit = report["historical_data_audit"]
    messages = report["failed_checks"] + report["warning_checks"]
    data_lines = [m for m in messages if m.startswith("Historical Data Audit:")]

    if audit.get("status") == "PASS":
        assert not data_lines, data_lines
        return

    assert data_lines, f"audit status {audit.get('status')} produced no rollup line"
    reason = (audit.get("failed_bounds") or [audit.get("reason")])[0]
    assert reason and reason in data_lines[0], (
        f"rollup says {data_lines[0]!r}, audit says {reason!r}")
