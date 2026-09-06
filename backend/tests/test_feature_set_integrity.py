from backend.ml.feature_generator_registry import feature_generator_registry

def test_feature_set_integrity():
    # Executes checks on registry setup vs metadata mappings
    feature_generator_registry.validate_feature_sets_coverage()
