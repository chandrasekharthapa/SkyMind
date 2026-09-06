"""Tests for ModelArtifact."""
import os
import tempfile
from backend.ml.model_artifact import ModelArtifact


def test_model_artifact_fields():
    art = ModelArtifact(
        model_path="/tmp/model.pkl",
        metadata_path="/tmp/model.json",
        report_path="/tmp/report.json",
    )
    assert art.model_path == "/tmp/model.pkl"
    assert art.metadata_path == "/tmp/model.json"
    assert art.importance_path is None
    assert art.optimization_path is None


def test_model_artifact_exists_false_when_missing():
    art = ModelArtifact(
        model_path="/nonexistent/path/model.pkl",
        metadata_path="/nonexistent/meta.json",
        report_path="/nonexistent/report.json",
    )
    assert art.exists() is False


def test_model_artifact_exists_true_when_present():
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        path = f.name
    try:
        art = ModelArtifact(
            model_path=path,
            metadata_path="/tmp/meta.json",
            report_path="/tmp/report.json",
        )
        assert art.exists() is True
    finally:
        os.unlink(path)


def test_model_artifact_to_dict():
    art = ModelArtifact(
        model_path="/a/b.pkl",
        metadata_path="/a/b.json",
        report_path="/a/report.json",
        registry_entry={"slot": "latest"},
    )
    d = art.to_dict()
    assert d["registry_entry"]["slot"] == "latest"
