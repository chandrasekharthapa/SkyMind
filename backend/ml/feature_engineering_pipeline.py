import logging
from datetime import datetime, timezone
from typing import Dict, Any, Union
import numpy as np
import pandas as pd
from backend.ml.feature_context import FeatureContext
from backend.ml.feature_vector import FeatureVector
from backend.ml.feature_generator_registry import feature_generator_registry
from backend.ml.feature_metadata import LEGACY_FEATURE_SET, FEATURE_SET_V1

logger = logging.getLogger(__name__)

FEATURE_PIPELINE_VERSION = "2.0.0"

class FeatureEngineeringPipeline:
    def build(self, context: FeatureContext, feature_set_version: str) -> FeatureVector:
        """Executes generators for a single inference prediction and builds a FeatureVector."""
        # 1. Select the expected feature definitions
        if feature_set_version == "legacy":
            expected_defs = LEGACY_FEATURE_SET
        elif feature_set_version == "feature_set_v1":
            expected_defs = FEATURE_SET_V1
        else:
            raise ValueError(f"Unknown feature set version: '{feature_set_version}'")

        expected_names = [f.name for f in expected_defs]

        # 2. Run all registered generators
        merged_features: Dict[str, Any] = {}
        for generator in feature_generator_registry.get_generators():
            try:
                gen_output = generator.transform(context)
                for f_name, val in gen_output.items():
                    if f_name in expected_names:
                        merged_features[f_name] = val
            except Exception as e:
                logger.error(f"Error in generator {generator.name} during transform: {e}")
                raise e

        # 3. Validation: check for missing required features and fill with np.nan per Zero Synthetic Policy
        final_features: Dict[str, Any] = {}
        for f_name in expected_names:
            val = merged_features.get(f_name)
            # Ensure missing values default strictly to np.nan or None
            if val is None or (isinstance(val, float) and np.isnan(val)):
                final_features[f_name] = np.nan
            else:
                final_features[f_name] = val

        # 4. Generate deterministic feature hash
        generation_time = datetime.now(timezone.utc)
        feature_hash = FeatureVector.compute_hash(final_features, feature_set_version)

        return FeatureVector(
            features=final_features,
            feature_set_version=feature_set_version,
            generation_timestamp=generation_time,
            feature_hash=feature_hash
        )

    def build_training_dataset(self, dataframe: pd.DataFrame, feature_set_version: str) -> pd.DataFrame:
        """Transforms a raw observations DataFrame into an engineered features training DataFrame."""
        if feature_set_version == "legacy":
            expected_defs = LEGACY_FEATURE_SET
        elif feature_set_version == "feature_set_v1":
            expected_defs = FEATURE_SET_V1
        else:
            raise ValueError(f"Unknown feature set version: '{feature_set_version}'")

        expected_names = [f.name for f in expected_defs]

        # 1. Construct training context
        context = FeatureContext(
            historical_data=dataframe,
            market_snapshot=None,
            prediction_context={},
            route_statistics={},
            airline_statistics={},
            booking_statistics={},
            current_timestamp=datetime.now(timezone.utc)
        )

        # 2. Execute all generators in registry order
        merged_series: Dict[str, pd.Series] = {}
        for generator in feature_generator_registry.get_generators():
            gen_output = generator.transform(context)
            for f_name, col_series in gen_output.items():
                if f_name in expected_names:
                    # Coerce value to Series
                    if not isinstance(col_series, pd.Series):
                        merged_series[f_name] = pd.Series(col_series, index=dataframe.index)
                    else:
                        merged_series[f_name] = col_series

        # 3. Construct the output DataFrame in the exact expected order
        final_df = pd.DataFrame(index=dataframe.index)
        for f_name in expected_names:
            if f_name in merged_series:
                final_df[f_name] = merged_series[f_name]
            elif f_name in dataframe.columns:
                final_df[f_name] = dataframe[f_name]
            else:
                # Default strictly to np.nan per Zero Synthetic Feature Policy
                final_df[f_name] = np.nan

        return final_df

feature_engineering_pipeline = FeatureEngineeringPipeline()
