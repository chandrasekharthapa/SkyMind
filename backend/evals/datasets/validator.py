"""Dataset Schema & Integrity Validator for SkyMind Evaluation Platform.

Rejects invalid datasets, missing provenance fields, or duplicate example IDs before execution.
"""

import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

REQUIRED_METADATA_FIELDS = [
    "id",
    "dataset_version",
    "source",
    "reviewed",
    "difficulty",
    "priority",
    "tier",
    "regression",
    "created_by",
    "tags",
    "inputs",
    "expected"
]


def validate_dataset_schema(records: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """Validates list of JSONL test case records against schema requirements."""
    errors = []
    seen_ids = set()

    for idx, rec in enumerate(records):
        rec_id = rec.get("id")
        if not rec_id:
            errors.append(f"Record #{idx}: missing required field 'id'")
            continue

        if rec_id in seen_ids:
            errors.append(f"Duplicate record ID detected: '{rec_id}'")
        seen_ids.add(rec_id)

        for field in REQUIRED_METADATA_FIELDS:
            if field not in rec:
                errors.append(f"Record '{rec_id}': missing required field '{field}'")

        if not isinstance(rec.get("inputs"), dict) or "query" not in rec.get("inputs", {}):
            errors.append(f"Record '{rec_id}': 'inputs' must be a dict containing 'query'")

        if not isinstance(rec.get("expected"), dict):
            errors.append(f"Record '{rec_id}': 'expected' must be a dict")

    is_valid = len(errors) == 0
    if not is_valid:
        logger.error(f"[DatasetValidator] Validation failed with {len(errors)} errors.")

    return is_valid, errors
