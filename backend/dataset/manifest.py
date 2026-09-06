"""Cryptographic Hash & Lineage Manifest Writer for SkyMind Dataset Pipeline v2.0."""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any
from backend.dataset.config import default_dataset_config


def compute_file_sha256(filepath: str) -> str:
    """Computes SHA256 checksum hash of exported dataset file."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


def generate_dataset_manifest(filepath: str, row_count: int) -> Dict[str, Any]:
    """Generates cryptographic lineage manifest for exported dataset file."""
    file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    sha256_hash = compute_file_sha256(filepath) if os.path.exists(filepath) else ""

    manifest = {
        "filename": os.path.basename(filepath),
        "filepath": filepath,
        "file_size_bytes": file_size,
        "sha256": sha256_hash,
        "total_rows": row_count,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": default_dataset_config.dataset_version,
        "schema_version": default_dataset_config.schema_version,
        "feature_version": default_dataset_config.feature_version,
        "collector_version": default_dataset_config.collector_version,
        "pipeline_version": default_dataset_config.pipeline_version,
    }

    manifest_path = filepath + ".manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, indent=2))

    return manifest
