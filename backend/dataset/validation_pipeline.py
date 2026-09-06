"""Validation Pipeline Coordinator for SkyMind Dataset Pipeline v2.0.

Orchestrates sequential execution of modular validation plugins:
Schema -> Chronology -> Duplicate -> TimeSeries -> Anomaly
"""

import logging
from typing import List, Dict, Any, Tuple
import pandas as pd
from backend.dataset.plugins.base import BaseValidationPlugin, ValidationPluginResult
from backend.dataset.plugins.schema_plugin import SchemaValidationPlugin
from backend.dataset.plugins.chronology_plugin import ChronologyValidationPlugin
from backend.dataset.plugins.duplicate_plugin import DuplicateValidationPlugin
from backend.dataset.plugins.time_series_plugin import TimeSeriesIntegrityPlugin
from backend.dataset.plugins.anomaly_plugin import AnomalyValidationPlugin

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """Orchestrates modular validation plugin pipeline."""

    def __init__(self, plugins: List[BaseValidationPlugin] = None):
        self.plugins = plugins or [
            SchemaValidationPlugin(),
            ChronologyValidationPlugin(),
            DuplicateValidationPlugin(),
            TimeSeriesIntegrityPlugin(),
            AnomalyValidationPlugin()
        ]

    def process(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[ValidationPluginResult]]:
        """Processes DataFrame through all registered validation plugins sequentially."""
        current_df = df.copy()
        results: List[ValidationPluginResult] = []

        logger.info(f"[ValidationPipeline] Starting validation pipeline across {len(current_df)} rows...")
        for plugin in self.plugins:
            current_df, res = plugin.validate(current_df)
            results.append(res)
            logger.info(f"[ValidationPipeline] Plugin '{plugin.name}': Passed={res.passed}, Rejected={res.rejected_rows_count}")

        logger.info(f"[ValidationPipeline] Finished validation pipeline. Cleaned count: {len(current_df)}")
        return current_df, results


validation_pipeline = ValidationPipeline()
