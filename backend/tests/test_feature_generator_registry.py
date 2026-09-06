import pytest
from backend.ml.feature_generator_registry import feature_generator_registry

def test_registry_feature_uniqueness():
    generators = feature_generator_registry.get_generators()
    assert len(generators) == 7
    
    # Verify no two generators claim the same feature column
    all_features = []
    for g in generators:
        for f in g.feature_names:
            assert f not in all_features, f"Duplicate feature '{f}' found in generator {g.name}"
            all_features.append(f)
