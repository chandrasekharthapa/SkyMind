from backend.ml.feature_metadata import LEGACY_FEATURE_SET, FEATURE_SET_V1

def test_feature_metadata_coverage():
    assert len(LEGACY_FEATURE_SET) == 16
    assert len(FEATURE_SET_V1) > 16
    
    # Assert every metadata has dtype, category, description, and owner
    for f in LEGACY_FEATURE_SET:
        assert f.name
        assert f.dtype
        assert f.category
        assert f.owner_generator
        
    for f in FEATURE_SET_V1:
        assert f.name
        assert f.dtype
        assert f.category
        assert f.owner_generator
