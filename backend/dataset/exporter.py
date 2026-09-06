"""Dataset Exporter & Quality Report Generator for SkyMind Dataset Pipeline v2.0."""

import os
import json
import logging
from typing import Dict, Any, Tuple
import pandas as pd
from backend.dataset.config import default_dataset_config
from backend.dataset.itinerary import attach_itinerary_id_to_row
from backend.dataset.snapshot import attach_snapshot_metadata, compute_snapshot_sequences
from backend.dataset.features import engineer_dataset_features
from backend.dataset.validation_pipeline import validation_pipeline
from backend.dataset.statistics import dataset_statistics_engine
from backend.dataset.manifest import generate_dataset_manifest

logger = logging.getLogger(__name__)


class DatasetExporter:
    """Exports dataset v2.0 with validation, feature engineering, and quality report generation."""

    def export(self, df_raw: pd.DataFrame, output_dir: str = None) -> Tuple[str, Dict[str, Any]]:
        """Processes raw dataset DataFrame, engineers features, validates, and exports CSV/Parquet + reports."""
        out_dir = output_dir or default_dataset_config.output_directory
        os.makedirs(out_dir, exist_ok=True)

        if df_raw.empty:
            logger.warning("[DatasetExporter] Provided raw DataFrame is empty.")
            return "", {"status": "EMPTY"}

        # 1. Attach Itinerary ID & Snapshot Metadata
        records = df_raw.to_dict(orient="records")
        processed_records = []
        for idx, rec in enumerate(records):
            rec = attach_itinerary_id_to_row(rec)
            rec = attach_snapshot_metadata(rec, sequence=1)
            processed_records.append(rec)

        df_processed = pd.DataFrame(processed_records)
        df_processed = compute_snapshot_sequences(df_processed)

        # 2. Engineer Derived Domain Features
        df_features = engineer_dataset_features(df_processed)

        # 3. Validation Pipeline Processing
        df_cleaned, plugin_results = validation_pipeline.process(df_features)

        # 4. Generate Statistics & Quality Report
        stats_report = dataset_statistics_engine.compute(df_raw, df_cleaned, plugin_results)

        # Check for export abort on days_until_dep mismatches
        mismatches = stats_report["summary"]["days_until_dep_mismatches"]
        if mismatches > 0:
            logger.error(f"[DatasetExporter] Aborting export: {mismatches} days_until_dep mismatches detected!")
            raise ValueError(f"Export aborted: {mismatches} days_until_dep calendar date mismatches detected.")

        # 5. Export Dataset CSV & Parquet
        csv_filename = os.path.join(out_dir, "flight_price_dataset_v2.0.csv")
        df_cleaned.to_csv(csv_filename, index=False)
        logger.info(f"[DatasetExporter] Exported dataset CSV to '{csv_filename}' ({len(df_cleaned)} rows).")

        # Export quality_report.json
        report_json_path = os.path.join(out_dir, "quality_report.json")
        with open(report_json_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(stats_report, indent=2))

        # Generate cryptographic manifest
        generate_dataset_manifest(csv_filename, len(df_cleaned))

        return csv_filename, stats_report


dataset_exporter = DatasetExporter()
