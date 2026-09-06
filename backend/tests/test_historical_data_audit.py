"""What the historical-data audit reports, and where it writes it.

The single test here used to be `run_audit()` followed by
`assert report["total_observations"] > 0`, which had two problems.

It required a populated live Supabase, so it failed in any clean checkout with
`AssertionError: assert 0 > 0` — a failure that says nothing about the audit and
everything about the environment. An audit that correctly reports an empty corpus
is working; the test now skips on that, quoting the audit's own reason.

And `run_audit()` wrote to the repository root, where `historical_data_report.json`
is a tracked file, so *running this test modified version control*. Every test
below passes an explicit destination under `tmp_path`. See
`backend.utils.report_paths`.
"""

import json
import os

import pytest

from backend.services.booking_curve_definition import BOOKING_CURVE_KEYS
from backend.services.historical_data_audit import (
    MAX_DUPLICATE_PCT,
    MIN_OBSERVATIONS,
    historical_data_audit_service,
)


def _audit(tmp_path):
    dest = os.path.join(str(tmp_path), "historical_data_report.json")
    return historical_data_audit_service.run_audit(destination=dest), dest


def test_the_audit_writes_the_report_it_returns(tmp_path):
    """The file on disk must be the report handed back, at the path asked for.

    `test_production_readiness` asserted `os.path.exists()` on the tracked root
    copy, which is true before any test runs and therefore could not fail for its
    stated reason. Pointing at `tmp_path` makes the assertion mean something: the
    file is absent until this call creates it.
    """
    report, dest = _audit(tmp_path)

    assert report.get("report_written_to") == dest, (
        f"write outcome: {report.get('report_write_error') or report.get('report_written_to')}")
    assert os.path.isfile(dest)
    with open(dest) as fh:
        assert json.load(fh) == report


def test_every_measured_figure_is_present_and_gated(tmp_path):
    """A figure the report publishes but the status ignores is the old bug.

    The gate was `total_obs >= 100 and missing_pct <= 50.0`, so
    `duplicate_observation_percentage` was computed, written out and never
    consulted — the committed 2026-07-27 report reads 20.0% duplicates and
    `status: "PASS"`.
    """
    report, _ = _audit(tmp_path)

    for key in ("total_observations", "route_coverage_count", "distinct_booking_curves",
                "missing_value_percentage", "duplicate_observation_percentage",
                "observations_per_booking_curve_avg", "observations_per_route_avg",
                "feature_completeness_ratio", "status", "failed_bounds"):
        assert key in report, f"{key} missing from {sorted(report)}"

    assert report["status"] in ("PASS", "FAIL")
    # PASS and an empty breach list are the same statement; disagreement means the
    # gate and the reported reasons were computed from different things.
    assert (report["status"] == "PASS") == (not report["failed_bounds"]), report


def test_a_duplicate_heavy_corpus_cannot_pass(tmp_path):
    """The bound that the old gate did not have. Skips when there is no corpus."""
    report, _ = _audit(tmp_path)

    if report["total_observations"] < 1:
        pytest.skip(f"no corpus to grade: {report.get('reason')}")

    if report["duplicate_observation_percentage"] > MAX_DUPLICATE_PCT:
        assert report["status"] == "FAIL", (
            f"{report['duplicate_observation_percentage']}% duplicates exceeds the "
            f"{MAX_DUPLICATE_PCT}% bound but the status is {report['status']}")
        assert any("duplicate" in b for b in report["failed_bounds"]), report["failed_bounds"]


def test_curve_density_is_counted_over_the_booking_curve_key(tmp_path):
    """Observations per *curve*, not per route.

    `booking_curve_density_avg` was `total_obs / route_count`. A route carries
    many flight numbers across many departure dates, so that figure is
    observations per route published under the name of observations per curve —
    125.0 on the committed report. Curves are at least as numerous as routes, so
    per-curve density can never exceed per-route density; asserting that ordering
    is what catches a reversion to the old formula.
    """
    report, _ = _audit(tmp_path)

    if report["total_observations"] < 1:
        pytest.skip(f"no corpus to grade: {report.get('reason')}")

    key_cols = report["booking_curve_key_columns"]
    assert set(key_cols) <= set(BOOKING_CURVE_KEYS), key_cols
    assert report["distinct_booking_curves"] >= report["route_coverage_count"] or not key_cols, (
        f"{report['distinct_booking_curves']} curves over {key_cols} is fewer than "
        f"{report['route_coverage_count']} routes")
    assert (report["observations_per_booking_curve_avg"]
            <= report["observations_per_route_avg"] + 1e-9), report


def test_a_populated_corpus_meets_the_observation_floor(tmp_path):
    """The original assertion, made conditional on there being data at all."""
    report, _ = _audit(tmp_path)

    if report["total_observations"] < 1:
        pytest.skip(
            "the audit reports an empty corpus, which is a correct audit of an "
            f"empty database rather than a failure: {report.get('reason')}")

    assert report["total_observations"] >= MIN_OBSERVATIONS, (
        f"{report['total_observations']} observations is below the "
        f"{MIN_OBSERVATIONS} the audit requires; breaches: {report['failed_bounds']}")
