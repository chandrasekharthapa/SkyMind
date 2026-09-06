"""
SkyMind — Unified Daily Pipeline
Handles: Ingestion, Alerts, Retraining, and Persistence.
Designed for GitHub Actions.

Two things about this file were wrong in ways that made the scheduled job
useless as a signal, and both are fixed below.

**Every task swallowed its own failure.** Each of the three functions wrapped its
body in `except Exception as e: logger.error(...)` and returned normally, and
`__main__` called them for their side effects without looking at anything. A run
in which the scraper never connected, no alert was checked and the retrain
crashed logged three errors and exited 0, so the workflow went green. Each task
now reports whether it succeeded and the process exits non-zero if any did not.
The tasks still all run — one failing does not skip the others, which is why the
result is collected rather than raised.

**The imports loaded a second copy of the application.** They were
`from services.scheduler import ...`, `from ml.price_model import ...` and
`from database.database import ...`, resolved because the workflow sets
`PYTHONPATH` to the *backend* directory and this file additionally appended it.
Every other module in the project imports `backend.x`, so both spellings resolve
and each creates a distinct module object: two `database` singletons, two cached
predictors, two sets of circuit-breaker state. The retrain then fits and writes
one predictor while the API serves the other. Imports are `backend.x` here, this
file puts the repository root on `sys.path` rather than `backend/`, and the
workflow's PYTHONPATH was changed to match.
"""

import os
import logging
import sys
from datetime import datetime

# The repository root — the directory that *contains* `backend` — so that
# `import backend.x` resolves. `backend` itself is deliberately not added: that
# is what allowed the shadow `services.x` / `ml.x` / `database.x` imports.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SkyMindPipeline")


def run_ingestion() -> bool:
    logger.info(">>> TASK 1: Starting Live Market Data Ingestion...")
    try:
        from backend.services.scheduler import _collect_popular_routes
        _collect_popular_routes()
        logger.info("Ingestion complete.")
        return True
    except Exception as e:
        logger.error(f"Ingestion failed: {type(e).__name__}: {e}", exc_info=True)
        return False


def run_alerts() -> bool:
    logger.info(">>> TASK 2: Checking Price Alerts...")
    try:
        from backend.services.scheduler import _check_price_alerts
        _check_price_alerts()
        logger.info("Alert check complete.")
        return True
    except Exception as e:
        logger.error(f"Alert check failed: {type(e).__name__}: {e}", exc_info=True)
        return False


def run_retraining() -> bool:
    logger.info(">>> TASK 3: Retraining XGBoost Model...")
    try:
        from backend.ml.price_model import get_predictor, MODEL_PATH
        from backend.database.database import database as db

        predictor = get_predictor()
        predictor.train()

        logger.info(">>> TASK 4: Uploading Model to Supabase Storage...")
        if not os.path.exists(MODEL_PATH):
            # Was a bare `logger.error` with no effect on the exit status, so a
            # retrain that produced no artifact reported success. It is a failure:
            # either train() did not write, or it wrote somewhere else.
            logger.error(f"Model file not found after training: {MODEL_PATH}")
            return False

        if not db.upload_model(MODEL_PATH):
            logger.error("Model persistence failed.")
            return False

        logger.info("Model persistence successful.")
        return True
    except Exception as e:
        logger.error(f"Retraining failed: {type(e).__name__}: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    logger.info("=== SkyMind Pipeline Initialized ===")
    start_time = datetime.now()

    # Run the whole sequence regardless of individual failures, then report.
    # `sys.exit(1)` used to be reachable from exactly one branch of one task;
    # every other way this pipeline can fail exited 0.
    results = {
        "ingestion": run_ingestion(),
        "alerts": run_alerts(),
        "retraining": run_retraining(),
    }

    duration = (datetime.now() - start_time).total_seconds()
    failed = [name for name, ok in results.items() if not ok]

    if failed:
        logger.error(
            "=== SkyMind Pipeline FAILED in %.1fs — failed task(s): %s ===",
            duration, ", ".join(failed),
        )
        sys.exit(1)

    logger.info(f"=== SkyMind Pipeline Completed in {duration:.1f}s ===")
