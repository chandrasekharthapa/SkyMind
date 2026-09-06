"""Model Artifact.

Paths to every file written to disk for a single training run.
ModelTrainer returns both a TrainingResult and a ModelArtifact.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


@dataclass
class ModelArtifact:
    """Filesystem paths for all files produced by one training run."""

    model_path: str               # path to .pkl model file
    metadata_path: str            # path to metadata .json
    report_path: str              # path to training_report.json
    importance_path: Optional[str] = None     # path to feature_importance.json (if available)
    optimization_path: Optional[str] = None  # path to best_params.json (if Optuna ran)
    registry_entry: Optional[Dict[str, Any]] = None  # what was written to registry.json

    # ──────────────────────────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def exists(self) -> bool:
        """True only if the primary model file is present on disk."""
        return os.path.isfile(self.model_path)
