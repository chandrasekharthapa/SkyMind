from datetime import datetime, timezone
from backend.ml.feature_vector import FeatureVector

def test_feature_vector_hashing():
    feats1 = {"a": 1.0, "b": 2.0}
    feats2 = {"b": 2.0, "a": 1.0}
    
    hash1 = FeatureVector.compute_hash(feats1, "v1")
    hash2 = FeatureVector.compute_hash(feats2, "v1")
    
    # Ordering differences should not affect the hash since we sort the keys internally
    assert hash1 == hash2
    
    feats3 = {"a": 1.000001, "b": 2.0}
    hash3 = FeatureVector.compute_hash(feats3, "v1")
    assert hash1 != hash3
