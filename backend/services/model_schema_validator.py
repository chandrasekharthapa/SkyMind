"""Model Schema Validator.

Validates that feature names, count, and sorting order conform exactly to the
expected feature schema from the deployed ModelRegistry to ensure training/inference parity.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ModelSchemaValidator:
    @staticmethod
    def validate_schema(features: Dict[str, Any], expected_features: List[str], expected_version: Optional[str] = None) -> None:
        """Validates features shape, order, names, missing, and unexpected features."""
        feature_names = list(features.keys())
        
        # 1. Validate duplicates (if duplicates were somehow passed or in registry)
        if len(feature_names) != len(set(feature_names)):
            err_msg = "Duplicate features found in the input dictionary keys."
            logger.error(err_msg)
            raise ValueError(err_msg)

        # 2. Validate counts
        if len(feature_names) != len(expected_features):
            err_msg = f"Feature count mismatch: expected {len(expected_features)} columns, but got {len(feature_names)} features."
            logger.error(err_msg)
            raise ValueError(err_msg)

        # 3. Check for missing features
        missing = [f for f in expected_features if f not in features]
        if missing:
            err_msg = f"Missing required features: {missing}"
            logger.error(err_msg)
            raise ValueError(err_msg)

        # 4. Check for unexpected features
        unexpected = [f for f in feature_names if f not in expected_features]
        if unexpected:
            err_msg = f"Unexpected features found: {unexpected}"
            logger.error(err_msg)
            raise ValueError(err_msg)
            
        # 5. Validate exact order and names
        for idx, (got_name, expected_name) in enumerate(zip(feature_names, expected_features)):
            if got_name != expected_name:
                err_msg = (
                    f"Feature schema mismatch at index {idx}: expected name '{expected_name}', "
                    f"but got '{got_name}'."
                )
                logger.error(err_msg)
                raise ValueError(err_msg)
                
        logger.info("Model Schema Validation passed successfully. Parity verified.")

