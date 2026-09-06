from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import Dict, Any, List

from backend.services.system_info_service import system_info_service
from backend.services.validation_service import validation_service
from backend.ml.price_model import get_predictor

router = APIRouter()

# One place decides what this service claims about itself.
SCHEMA_VERSION = "1.0.0"
API_VERSION = "v1"
BACKEND_VERSION = "11.0.0"


@router.get("/health", tags=["System"])
async def get_health() -> Dict[str, Any]:
    """Liveness plus the one dependency that decides whether answers are possible.

    This reported `"status": "ok"` unconditionally and `"model": "lazy"` whenever
    the predictor was untrained. Both were wrong in the same direction. "ok" was a
    statement about the process, not the service: a deployment whose every
    prediction request returns 503 because no artifact loaded reported healthy, so
    an uptime check watching this endpoint would never fire. And "lazy" says the
    model has not been asked for yet — it loads on first use — when in fact
    `get_predictor()` has already tried, already failed, and recorded why in
    `load_error`. The distinction matters operationally: "lazy" means wait, "failed"
    means go look at the artifacts.

    `degraded` rather than a non-2xx status, because the process is serving and a
    load balancer should not pull it: search, airports and the chatbot do not need
    the model. The prediction endpoints refuse on their own.
    """
    predictor = get_predictor()
    trained = bool(getattr(predictor, "_trained", False))
    load_error = getattr(predictor, "load_error", None)
    refused = list(getattr(predictor, "refused_artifacts", []) or [])

    if trained:
        model_state = "ready"
    elif load_error or refused:
        model_state = "failed"
    else:
        model_state = "lazy"

    return {
        "schema_version": SCHEMA_VERSION,
        "api_version": API_VERSION,
        "backend_version": BACKEND_VERSION,
        "status": "ok" if trained else "degraded",
        "model": model_state,
        # Why there is no model, and which artifacts were declined. Recorded on the
        # predictor since the leak audit and published nowhere until now, so a
        # directory full of .pkl files that all fail the audit looked identical to
        # an empty one from outside the process.
        "model_load_error": load_error,
        "refused_artifacts": refused,
        "degraded_capabilities": (
            [] if trained else ["price_prediction", "fare_forecast"]
        ),
        # Was "SKYMIND_INTELLIGENCE", which names the product, not a source. What a
        # caller wants to know here is whether the numbers came from a model.
        "data_source": "trained_model" if trained else "none",
        "time": datetime.now(timezone.utc).isoformat()
    }


@router.get("/info", tags=["System"])
async def get_info() -> Dict[str, Any]:
    return system_info_service.get_system_info()


@router.get("/version", tags=["System"])
async def get_version() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "api_version": API_VERSION,
        "backend_version": BACKEND_VERSION,
    }


@router.get("/validation", tags=["System"])
@router.get("/validation/latest", tags=["System"])
async def get_latest_validation() -> Dict[str, Any]:
    report = validation_service.get_latest_report()
    if not report:
        raise HTTPException(status_code=404, detail="No validation reports found.")

    # Inject API meta
    report["schema_version"] = SCHEMA_VERSION
    report["api_version"] = API_VERSION
    report["backend_version"] = BACKEND_VERSION
    return report


@router.get("/validation/history", tags=["System"])
async def get_validation_history() -> List[Dict[str, Any]]:
    return validation_service.get_history()


@router.get("/validation/{timestamp}", tags=["System"])
async def get_validation_by_timestamp(timestamp: str) -> Dict[str, Any]:
    report = validation_service.get_report_by_timestamp(timestamp)
    if not report:
        raise HTTPException(status_code=404, detail=f"No validation report found for timestamp matching: {timestamp}")
    report["schema_version"] = SCHEMA_VERSION
    report["api_version"] = API_VERSION
    report["backend_version"] = BACKEND_VERSION
    return report


@router.get("/model/metadata", tags=["System"])
async def get_model_metadata() -> Dict[str, Any]:
    return system_info_service.get_model_metadata()
