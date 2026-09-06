"""Abstract Base Validation Plugin for SkyMind Dataset Pipeline."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple
import pandas as pd
from pydantic import BaseModel, Field


class ValidationPluginResult(BaseModel):
    plugin_name: str
    passed: bool = True
    rejected_rows_count: int = 0
    errors: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class BaseValidationPlugin(ABC):
    """Abstract base class for all modular dataset validation plugins."""

    name: str = "base_plugin"

    @abstractmethod
    def validate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, ValidationPluginResult]:
        """Validates DataFrame and returns (cleaned_df, plugin_result)."""
        pass
