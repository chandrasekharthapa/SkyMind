"""Central Configuration for SkyMind Flight Price Dataset Pipeline v2.0."""

import os
from typing import Optional
from pydantic import BaseModel, Field

#: `backend/dataset/`, resolved from this file. `output_directory` was the relative
#: string "backend/dataset/exports", so where an export landed depended on the process's
#: working directory: from the repository root, in the tracked tree (three files are
#: still in the index from that — see the `.gitignore` note); from `backend/`, in a
#: `backend/backend/` that nothing reads. Same defect as `evals/config.py` had.
_DATASET_DIR = os.path.dirname(os.path.abspath(__file__))

#: Default destination for dataset exports. Gitignored.
EXPORTS_DIR = os.path.join(_DATASET_DIR, "exports")


def default_export_directory() -> str:
    """Absolute export directory, overridable by `DATASET_EXPORT_DIR`.

    Read at construction time, not import time, so a test can redirect it.
    """
    return os.getenv("DATASET_EXPORT_DIR", "").strip() or EXPORTS_DIR


class DatasetConfig(BaseModel):
    dataset_version: str = Field(default="2.0.0", description="Data release artifact version")
    schema_version: str = Field(default="2.0.0", description="Column schema definition version")
    feature_version: str = Field(default="2.0.0", description="Feature engineering pipeline version")
    collector_version: str = Field(default="2.0.0", description="Scraper & revisit scheduler version")
    pipeline_version: str = Field(default="2.0.0", description="Data processing pipeline version")
    validation_rules_version: str = Field(default="2.0.0", description="Validation rules version")

    validation_mode: str = Field(default="STRICT", description="Validation mode: STRICT, WARN, or REPAIR")
    max_allowed_mismatch_rate: float = Field(default=0.0, description="Max allowed rate for days_until_dep error (0.0 = zero tolerance)")
    batch_size: int = Field(default=50000, description="Processing batch size for chunked validation")
    storage_format: str = Field(default="parquet", description="Default export storage format: parquet or csv")
    output_directory: str = Field(default_factory=default_export_directory,
                                 description="Export output directory (absolute)")


default_dataset_config = DatasetConfig()
