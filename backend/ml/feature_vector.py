from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Any
import hashlib
import pandas as pd

@dataclass(frozen=True)
class FeatureVector:
    features: Mapping[str, Any]
    feature_set_version: str
    generation_timestamp: datetime
    feature_hash: str

    @staticmethod
    def compute_hash(features: Mapping[str, Any], feature_set_version: str) -> str:
        """Generates deterministic SHA256 hash from feature values and version."""
        serialized_parts = []
        sorted_keys = sorted(features.keys())
        for key in sorted_keys:
            val = features[key]
            if val is None or (isinstance(val, float) and pd.isna(val)):
                str_val = "nan"
            elif isinstance(val, bool):
                str_val = "true" if val else "false"
            elif isinstance(val, float):
                str_val = f"{val:.6f}"
            else:
                str_val = str(val)
            serialized_parts.append(f"{key}:{str_val}")
        
        raw_str = feature_set_version + "|" + ",".join(sorted_keys) + "|" + ",".join(serialized_parts)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
