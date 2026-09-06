"""CLI Explicit LangSmith Dataset Sync Module for SkyMind Platform.

Dataset synchronization with LangSmith occurs ONLY when this CLI module is explicitly invoked:
    python -m backend.evals.sync
"""

import sys
import logging
from backend.evals.datasets.loader import dataset_loader
from backend.services.langsmith_tracer import langsmith_tracer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def sync_datasets_to_langsmith():
    """Reads versioned Git JSONL datasets and pushes to LangSmith Datasets API."""
    if not langsmith_tracer.client:
        logger.warning("[LangSmithSync] Skipping sync: LangSmith client is not configured or disabled.")
        return False

    records = dataset_loader.load_dataset(version="2.0.0", tier="full")
    dataset_name = f"skymind_golden_v2.0"

    try:
        # Check if dataset exists or create
        try:
            ds = langsmith_tracer.client.read_dataset(dataset_name=dataset_name)
            logger.info(f"[LangSmithSync] Found existing dataset '{dataset_name}' (ID: {ds.id}).")
        except Exception:
            ds = langsmith_tracer.client.create_dataset(
                dataset_name=dataset_name,
                description="SkyMind Copilot Golden Evaluation Dataset v2.0"
            )
            logger.info(f"[LangSmithSync] Created new dataset '{dataset_name}' (ID: {ds.id}).")

        # Sync examples
        for rec in records:
            langsmith_tracer.client.create_example(
                inputs=rec.get("inputs", {}),
                outputs=rec.get("expected", {}),
                dataset_id=ds.id,
                metadata={
                    "id": rec.get("id"),
                    "dataset_version": rec.get("dataset_version"),
                    "source": rec.get("source"),
                    "tier": rec.get("tier"),
                    "tags": rec.get("tags")
                }
            )

        logger.info(f"[LangSmithSync] Successfully synchronized {len(records)} records to LangSmith dataset '{dataset_name}'.")
        return True
    except Exception as e:
        logger.error(f"[LangSmithSync] Sync error: {e}")
        return False


if __name__ == "__main__":
    success = sync_datasets_to_langsmith()
    sys.exit(0 if success else 1)
