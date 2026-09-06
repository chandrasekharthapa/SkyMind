import pytest
import os
import json
import tempfile
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.validation_service import ValidationService
from backend.services.system_info_service import system_info_service

client = TestClient(app)

def test_validation_service_empty_dir():
    """Verify ValidationService handles empty or missing directories gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ValidationService(history_dir=tmpdir)
        assert svc.get_latest_report() is None
        assert svc.get_history() == []
        assert svc.get_report_by_timestamp("2026-07-21") is None

def test_validation_service_caching_and_history():
    """Verify ValidationService correctly loads and caches reports."""
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ValidationService(history_dir=tmpdir)
        
        # Write dummy report
        report_data = {
            "timestamp": "2026-07-21T18:00:00Z",
            "overall_status": "PASS",
            "readiness_score": 90,
            "feature_set_version": "feature_set_v1",
            "chronology": {"status": "PASS", "warnings": [], "errors": [], "metrics": {}}
        }
        
        report_path = os.path.join(tmpdir, "validation_2026-07-21T18_00_00Z.json")
        with open(report_path, "w") as f:
            json.dump(report_data, f)
            
        latest = svc.get_latest_report()
        assert latest is not None
        assert latest["readiness_score"] == 90
        
        # Test history retrieval
        hist = svc.get_history()
        assert len(hist) == 1
        assert hist[0]["readiness_score"] == 90
        
def test_ingestion_db_payload_schema_compliance():
    """Verify MarketDataController.get_db_payload excludes non-existent database columns."""
    from backend.services.ingestion_controller import MarketDataController
    payload = MarketDataController.format_payload('DEL', 'BOM', '6E', 5000.0, '2026-08-20', 10)
    db_payload = MarketDataController.get_db_payload(payload)
    
    # Ensure invalid columns that caused PGRST204 are filtered out
    invalid_cols = {"price_change_1d", "price_change_3d", "demand_score", "seasonality_factor"}
    for col in invalid_cols:
        assert col not in db_payload

def test_confidence_scaling_and_bounding():
    """Verify PredictionFormatter bounds confidence strictly between 0 and 100%."""
    from backend.services.prediction_formatter import PredictionFormatter
    
    # Decision with 0.85 (decimal ratio)
    res1 = PredictionFormatter.format_decision({"confidence": 0.85}, "RISING", 0.75)
    assert res1["confidence"] == 85.0
    
    # Decision with 85.0 (already percentage)
    res2 = PredictionFormatter.format_decision({"confidence": 85.0}, "RISING", 0.75)
    assert res2["confidence"] == 85.0
    
    # Decision with out-of-bound float (> 100%)
    res3 = PredictionFormatter.format_decision({"confidence": 3500.0}, "RISING", 0.75)
    assert res3["confidence"] == 100.0

def test_system_info_service():
    """Verify SystemInfoService retrieves structured config and model metadata."""
    info = system_info_service.get_system_info()
    assert info["schema_version"] == "1.0.0"
    assert info["api_version"] == "v1"
    
    meta = system_info_service.get_model_metadata()
    assert meta["model_name"] == "FareForecastEstimator"
    assert "validation_metrics" in meta

def test_system_router_endpoints():
    """Verify System router HTTP endpoints return successful versioned outputs."""
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    body = response.json()
    # This asserted `status == "ok"`, which the endpoint returned unconditionally —
    # including on a deployment where every prediction request 503s because no
    # artifact loaded. The status now tracks whether a model is serving, so the
    # assertion is on the coupling rather than on the literal, and it holds in both
    # states without needing a trained model.
    assert body["status"] in ("ok", "degraded")
    assert (body["status"] == "ok") == (body["model"] == "ready")
    assert body["degraded_capabilities"] == (
        [] if body["status"] == "ok" else ["price_prediction", "fare_forecast"])
    assert isinstance(body["refused_artifacts"], list)

    response = client.get("/api/v1/system/version")
    assert response.status_code == 200
    assert response.json()["api_version"] == "v1"

    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    assert "validator_version" in response.json()


def test_the_root_health_endpoint_is_the_same_endpoint():
    """`/health` was a second copy that could disagree with the router's.

    Render's health check points at the unprefixed one, so the copy deciding
    whether a deploy counted as live was not the copy anything else read. It
    delegates now; the only difference is the legacy `version` key.
    """
    root = client.get("/health")
    routed = client.get("/api/v1/system/health")
    assert root.status_code == routed.status_code == 200

    a, b = root.json(), routed.json()
    assert a["version"] == a["backend_version"]
    a.pop("version")
    # `time` is generated per request.
    a.pop("time"), b.pop("time")
    assert a == b


def test_a_refused_artifact_is_visible_from_outside_the_process(monkeypatch):
    """The whole point of recording a refusal is that an operator can see it.

    `load()` appends a reason for every artifact whose metadata lacks a clean
    leak-audit block, and `get_predictor()` records the load exception. Neither
    reached an endpoint, so a models directory in which every artifact fails the
    audit looked identical from outside to one that was simply empty.
    """
    from backend.ml.price_model import get_predictor
    predictor = get_predictor()
    monkeypatch.setattr(predictor, "_trained", False, raising=False)
    monkeypatch.setattr(
        predictor, "refused_artifacts",
        ["horizon 3: no leak_audit block in metadata"], raising=False)
    monkeypatch.setattr(
        predictor, "load_error", "ValueError: refused 1 artifact(s)", raising=False)

    body = client.get("/api/v1/system/health").json()
    assert body["status"] == "degraded"
    assert body["model"] == "failed"
    assert body["refused_artifacts"] == ["horizon 3: no leak_audit block in metadata"]
    assert body["model_load_error"] == "ValueError: refused 1 artifact(s)"
    assert body["data_source"] == "none"

    info = client.get("/api/v1/system/info").json()
    assert info["refused_artifacts"] == ["horizon 3: no leak_audit block in metadata"]
    assert info["model_load_error"] == "ValueError: refused 1 artifact(s)"
    assert any(r.startswith("refused_artifacts:") for r in info["unavailable"]), \
        info["unavailable"]

    meta = client.get("/api/v1/system/model/metadata").json()
    assert meta["refused_artifacts"] == ["horizon 3: no leak_audit block in metadata"]


def test_an_untrained_model_is_reported_as_lazy_only_when_nothing_failed():
    """"lazy" means wait, "failed" means go look at the artifacts.

    Reporting a failed load as "lazy" told an operator the model had not been asked
    for yet, when `get_predictor()` had already tried and already recorded why.
    """
    from backend.ml.price_model import get_predictor
    predictor = get_predictor()
    trained = bool(getattr(predictor, "_trained", False))
    load_error = getattr(predictor, "load_error", None)
    refused = list(getattr(predictor, "refused_artifacts", []) or [])

    body = client.get("/api/v1/system/health").json()
    if trained:
        assert body["model"] == "ready"
    elif load_error or refused:
        assert body["model"] == "failed"
    else:
        assert body["model"] == "lazy"


def test_both_horizon_fields_come_from_the_registry():
    """`/info` published the literal 3 and `/model/metadata` the literal 0.

    Two endpoints of one service disagreeing about which horizon the deployed model
    answers, neither reading the artifacts — and 0 is the horizon
    `MIN_TRAINABLE_HORIZON_DAYS` rules out, since at horizon 0 the label is the
    observation's own price.
    """
    from backend.services.model_registry import model_registry
    expected = model_registry.prediction_horizon

    info = system_info_service.get_system_info()
    meta = system_info_service.get_model_metadata()
    assert info["prediction_horizon"] == expected
    assert meta["prediction_horizon"] == expected
    assert info["supported_horizons"] == model_registry.supported_horizons


def test_model_metadata_reports_a_missing_model_instead_of_returning_500(monkeypatch):
    """A designed refusal must not be served as a server fault.

    `get_model_metadata` read the metrics through `predictor.get_performance()`,
    which calls `ensure_ready()` -> `load()`, and `load()` raises FileNotFoundError
    when no artifact is loadable. So on a fresh checkout with an empty models
    directory — the exact state this endpoint exists to describe — the response was
    a 500, while `/health` returned `degraded` and `/info` returned
    `trained: false` with a reason for the same condition. A 500 makes a designed
    refusal indistinguishable from a crash to anything watching the API.

    Nothing had reached this path: the module needs fastapi and pytest, and the
    suite has never run in CI. It was found by booting the API against a real
    empty models directory.
    """
    from backend.ml.price_model import get_predictor
    predictor = get_predictor()

    def _no_artifacts_on_disk():
        raise FileNotFoundError("No prediction or forecasting models found on disk.")

    monkeypatch.setattr(predictor, "_trained", False, raising=False)
    monkeypatch.setattr(
        predictor, "get_performance", _no_artifacts_on_disk, raising=False)
    monkeypatch.setattr(
        predictor, "load_error",
        "FileNotFoundError: No prediction or forecasting models found on disk.",
        raising=False)
    monkeypatch.setattr(predictor, "refused_artifacts", [], raising=False)

    response = client.get("/api/v1/system/model/metadata")
    assert response.status_code == 200, response.text

    meta = response.json()
    assert meta["trained"] is False
    assert meta["validation_metrics"] is None
    assert meta["model_load_error"] == (
        "FileNotFoundError: No prediction or forecasting models found on disk.")
    assert any("no model is loaded" in reason for reason in meta["unavailable"]), \
        meta["unavailable"]

    # All three endpoints must describe the one condition the same way.
    assert client.get("/health").json()["status"] == "degraded"
    assert client.get("/api/v1/system/info").json()["trained"] is False
