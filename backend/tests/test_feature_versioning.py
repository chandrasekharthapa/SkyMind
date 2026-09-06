from backend.ml.feature_metadata import LEGACY_FEATURE_SET, FEATURE_SET_V1

def test_feature_versioning_isolation():
    legacy_names = {f.name for f in LEGACY_FEATURE_SET}
    v1_names = {f.name for f in FEATURE_SET_V1}
    
    # Assert version metadata flags are isolated
    for f in LEGACY_FEATURE_SET:
        assert f.feature_set_version == "legacy"
        
    for f in FEATURE_SET_V1:
        assert f.feature_set_version == "feature_set_v1"
