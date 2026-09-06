"""Test Suite for Feature Validation.

The report is written to `tmp_path`: the default destination used to be the
repository root, where `feature_validation_report.json` is tracked, so running
this test rewrote version-controlled content. See `backend.utils.report_paths`.
"""

import json
import os

import pandas as pd
import pytest

from backend.services.feature_validation import feature_validation_service


def _validate(df, tmp_path):
    dest = os.path.join(str(tmp_path), "feature_validation_report.json")
    return feature_validation_service.validate_features_dataframe(df, destination=dest), dest


def test_feature_validation_dataframe(tmp_path):
    data = {col: [1.0, 2.0] for col in feature_validation_service.expected_features}
    df = pd.DataFrame(data)

    report, dest = _validate(df, tmp_path)
    assert report["valid"] is True
    assert report["feature_completeness"] == 1.0
    assert report["missing_features"] == []
    assert report.get("report_written_to") == dest, (
        f"write outcome: {report.get('report_write_error')}")
    with open(dest) as fh:
        assert json.load(fh) == report


def test_determinism_is_reported_as_unchecked_rather_than_verified(tmp_path):
    """The field used to be the literal `True`.

    Nothing in this module builds features twice, and this method structurally
    cannot: it receives a finished frame. `production_readiness` copies the report
    verbatim into its own output, so the claim travelled.
    """
    df = pd.DataFrame({col: [1.0] for col in feature_validation_service.expected_features})

    report, _ = _validate(df, tmp_path)
    assert report["determinism_verified"] is None
    assert "not performed" in report["determinism_check"]


def test_an_empty_frame_still_produces_an_artifact(tmp_path):
    """The empty path used to return without writing.

    On an empty corpus the file therefore kept whatever the previous run left
    behind — a stale PASS describing a frame that no longer existed.
    """
    report, dest = _validate(pd.DataFrame(), tmp_path)

    assert report["valid"] is False
    assert report["reason"] == "DataFrame is empty or None"
    assert os.path.isfile(dest), "empty-frame validation wrote no report"
    with open(dest) as fh:
        assert json.load(fh) == report
