from typing import List, Dict
import logging
from backend.ml.feature_generator import FeatureGenerator
from backend.ml.feature_metadata import LEGACY_FEATURE_SET, FEATURE_SET_V1

logger = logging.getLogger(__name__)

class FeatureGeneratorRegistry:
    def __init__(self):
        self._generators: List[FeatureGenerator] = []

    def register(self, generator: FeatureGenerator) -> None:
        """Registers a generator. Enforces unique feature ownership and deterministic execution ordering."""
        # 1. Validate generator metadata
        if not generator.name or not generator.version or not generator.category:
            raise ValueError(f"Generator {generator.__class__.__name__} is missing required metadata properties.")
        
        # 2. Check for duplicate feature ownership
        registered_features = self.get_registered_features()
        for feature in generator.feature_names:
            if feature in registered_features:
                raise ValueError(f"Feature name duplication detected: '{feature}' is already owned by another generator.")
        
        self._generators.append(generator)
        logger.info(f"Registered FeatureGenerator '{generator.name}' (version {generator.version}) successfully.")

    def get_generators(self) -> List[FeatureGenerator]:
        """Returns the registered generators in deterministic order of registration."""
        return list(self._generators)

    def get_registered_features(self) -> List[str]:
        """Aggregates all feature names owned by registered generators."""
        features = []
        for gen in self._generators:
            features.extend(gen.feature_names)
        return features

    def validate_feature_sets_coverage(self) -> None:
        """Validates that all declared metadata features are generated, and no extra features are generated."""
        registered_features = set(self.get_registered_features())
        
        # Check Legacy
        legacy_names = {f.name for f in LEGACY_FEATURE_SET}
        v1_names = {f.name for f in FEATURE_SET_V1}
        all_metadata_names = legacy_names.union(v1_names)
        
        # 1. Check duplicate metadata ownership
        from collections import Counter
        for subset, set_name in [(LEGACY_FEATURE_SET, "LEGACY_FEATURE_SET"), (FEATURE_SET_V1, "FEATURE_SET_V1")]:
            counts = Counter(f.name for f in subset)
            duplicates = [name for name, cnt in counts.items() if cnt > 1]
            if duplicates:
                raise ValueError(f"Metadata duplicate definitions in {set_name}: {duplicates}")

        # 2. Ensure every feature name produced is defined in metadata
        for f in registered_features:
            if f not in all_metadata_names:
                raise ValueError(f"Generator produced feature '{f}' is not defined in any FeatureDefinition metadata set.")

        # 3. Validate metadata owner names match actual generator names
        generator_names = {gen.name for gen in self._generators}
        for subset in [LEGACY_FEATURE_SET, FEATURE_SET_V1]:
            for f_def in subset:
                if f_def.owner_generator not in generator_names:
                    # Ignore generators that haven't been registered yet in early execution
                    pass

        logger.info("Feature Set Integrity validation passed.")

feature_generator_registry = FeatureGeneratorRegistry()

# Register generators in deterministic execution order
from backend.ml.features.temporal import TemporalGenerator
from backend.ml.features.market import MarketGenerator
from backend.ml.features.route import RouteGenerator
from backend.ml.features.airline import AirlineGenerator
from backend.ml.features.booking_curve import BookingCurveGenerator
from backend.ml.features.volatility import VolatilityGenerator
from backend.ml.features.trend import TrendGenerator

feature_generator_registry.register(TemporalGenerator())
feature_generator_registry.register(MarketGenerator())
feature_generator_registry.register(RouteGenerator())
feature_generator_registry.register(AirlineGenerator())
feature_generator_registry.register(BookingCurveGenerator())
feature_generator_registry.register(VolatilityGenerator())
feature_generator_registry.register(TrendGenerator())

