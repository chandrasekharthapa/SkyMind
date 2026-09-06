"""Test Suite for Drift Detection Service.

`run_drift_analysis` publishes `None` scores with `overall_drift_status:
"UNMEASURABLE"` when too few observations carry a usable observation time to
separate an earlier window from a later one. The assertion here was
`0.0 <= report["feature_drift_score"] <= 1.0`, which raises `TypeError:
'<=' not supported between 'float' and 'NoneType'` on exactly that report — so
the refusal the service was taught to make would surface as a test error rather
than as the pass it is. The bound is now asserted only where a number exists, and
the absence is asserted to come with a reason.

The destination is `tmp_path` because the default used to be the repository root,
where `drift_report.json` is tracked; see `backend.utils.report_paths`.
"""

import os

import pytest

from backend.services.drift_detection import drift_detection_service

SCORES = ("feature_drift_score", "prediction_drift_score", "market_drift_score")


def _analysis(tmp_path):
    dest = os.path.join(str(tmp_path), "drift_report.json")
    return drift_detection_service.run_drift_analysis(destination=dest), dest


def test_drift_detection_run(tmp_path):
    report, dest = _analysis(tmp_path)

    for key in SCORES + ("overall_drift_status",):
        assert key in report, f"{key} missing from {sorted(report)}"
    assert report.get("report_written_to") == dest, (
        f"write outcome: {report.get('report_write_error')}")


def test_a_published_score_is_a_fraction_and_a_missing_one_is_explained(tmp_path):
    report, _ = _analysis(tmp_path)

    for key in SCORES:
        score = report[key]
        if score is None:
            assert report["overall_drift_status"] == "UNMEASURABLE", report
            assert report.get("reason"), "no score and no reason"
        else:
            assert 0.0 <= score <= 1.0, f"{key}={score}"


def test_a_measured_report_names_both_window_sizes(tmp_path):
    """A drift figure is a comparison of two windows, so both counts must be there.

    Without them the score is unfalsifiable: a reader cannot tell whether it came
    from 700 rows against 300 or from 2 against 1.
    """
    report, _ = _analysis(tmp_path)

    if report["overall_drift_status"] == "UNMEASURABLE":
        pytest.skip(f"drift not measurable: {report.get('reason')}")
    if report.get("reason") == "Insufficient observations for drift baseline":
        pytest.skip(report["reason"])

    assert report["baseline_sample_count"] > 0
    assert report["current_sample_count"] > 0
