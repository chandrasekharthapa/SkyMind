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


def _report_refusals(summary: dict) -> None:
    """Put each refused horizon on the GitHub run page, not only in the log.

    A `::warning` line becomes an annotation on the run, and the table goes into
    the job summary, so the reason a model was not published is visible without
    opening an 8,000-line log. Outside GitHub Actions this only logs.
    """
    rejected = summary.get("rejected_horizons") or {}
    details = summary.get("gate_details") or {}
    if not rejected:
        return
    rows = []
    for h in sorted(rejected, key=int):
        d = details.get(h) or details.get(str(h)) or {}
        if d:
            text = (
                f"model MAE Rs {d.get('model_mae')} vs fare-stays-same Rs "
                f"{d.get('fare_stays_same_mae')}; R2 {d.get('r2')}; MAPE {d.get('mape_pct')}%; "
                f"train/test rows {d.get('train_rows')}/{d.get('test_rows')} "
                f"(train to {d.get('train_end')}, test from {d.get('test_start')}); "
                f"empty features: {', '.join(d.get('empty_features') or []) or 'none'}; "
                f"failed: {', '.join(d.get('failed_criteria') or [])}"
            )
        else:
            text = str(rejected[h])
        rows.append((h, text))
        logger.warning("Horizon %sd not published: %s", h, text)
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    for h, text in rows:
        msg = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::warning title=Horizon {h}d not published::{msg}", flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("### Retraining\n\n| Horizon | Why it was not published |\n|---|---|\n")
                for h, text in rows:
                    fh.write(f"| {h}d | {text.replace('|', '/')} |\n")
                fh.write("\nThe live model is unchanged.\n")
        except OSError as exc:
            logger.warning("Could not write the job summary: %s", exc)


def run_retraining() -> bool:
    logger.info(">>> TASK 3: Retraining XGBoost Model...")
    try:
        from backend.ml.price_model import get_predictor, MODEL_PATH
        from backend.database.database import database as db

        predictor = get_predictor()
        summary = predictor.train() or {}

        _report_refusals(summary)

        if summary.get("insufficient_history"):
            # Not a failure: the label for horizon h is the same flight's fare h
            # days later, so nothing is learnable until the collector has watched
            # the same departures for several days. Logged loudly, exit 0, and
            # any previously uploaded model stays in place.
            logger.warning(
                "Retraining skipped: not enough history yet. Every horizon needs the "
                "same flights observed again 1/3/7 days later. %s",
                summary.get("rejected_horizons"))
            return True

        if not summary.get("trained_horizons"):
            # Nothing to upload. When every refusal was the quality gate or too
            # little history, the pipeline did its job — the models it could
            # build forecast worse than "the fare stays where it is" — so the run
            # passes, with the reasons on the run page (above). A daily red run
            # for an expected outcome trains everyone to ignore red runs. Any
            # other refusal (missing timestamps, an embargo that did not hold,
            # fares missing) is a defect and still fails the run.
            if summary.get("refused_only_on_quality_or_history"):
                logger.warning(
                    "Retraining published no model: none passed the quality gate yet. "
                    "The live model is unchanged. Per horizon: %s",
                    summary.get("rejected_horizons"))
                return True
            logger.error(
                "Retraining produced no model and at least one horizon was refused "
                "for a data or pipeline defect, not the quality gate. Per horizon: %s",
                summary.get("rejected_horizons"))
            return False

        logger.info(">>> TASK 4: Uploading Model to Supabase Storage...")
        if not summary.get("trained") or not os.path.exists(MODEL_PATH):
            # Was a bare `logger.error` with no effect on the exit status, so a
            # retrain that produced no artifact reported success. It is a failure:
            # either train() did not write, or it wrote somewhere else.
            logger.error(f"Model file not found after training: {MODEL_PATH}")
            return False

        # Every horizon's pickle and metadata, not just the legacy global
        # pickle: the serving path loads the per-horizon files.
        uploaded = db.upload_model_bundle(os.path.dirname(MODEL_PATH))
        logger.info("Model persistence successful: %s", ", ".join(uploaded))
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
