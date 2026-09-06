"""Tests for FeatureImportanceAnalyzer."""
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from backend.ml.feature_importance import FeatureImportanceAnalyzer, FeatureImportanceReport


def _train_simple_model():
    rng = np.random.default_rng(42)
    X = pd.DataFrame({"f_price": rng.uniform(100, 500, 200), "f_days": rng.integers(1, 30, 200).astype(float)})
    y = X["f_price"] * 0.8 + X["f_days"] * 5 + rng.normal(0, 10, 200)
    model = XGBRegressor(n_estimators=50, random_state=42)
    model.fit(X, y)
    return model, X, list(X.columns)


def test_feature_importance_report_fields():
    model, X, feature_names = _train_simple_model()
    analyzer = FeatureImportanceAnalyzer()
    report = analyzer.generate(
        model, feature_names, X,
        horizon=3, feature_set_version="feature_set_v1",
    )
    assert isinstance(report, FeatureImportanceReport)
    assert report.horizon == 3
    assert report.feature_set_version == "feature_set_v1"


def test_feature_importance_gain_present():
    model, X, feature_names = _train_simple_model()
    analyzer = FeatureImportanceAnalyzer()
    report = analyzer.generate(
        model, feature_names, X,
        horizon=3, feature_set_version="feature_set_v1",
    )
    assert len(report.gain) > 0
    assert all(v >= 0 for v in report.gain.values())


def test_feature_importance_weight_cover_present():
    model, X, feature_names = _train_simple_model()
    analyzer = FeatureImportanceAnalyzer()
    report = analyzer.generate(
        model, feature_names, X,
        horizon=3, feature_set_version="feature_set_v1",
    )
    assert len(report.weight) > 0
    assert len(report.cover) > 0


def test_feature_importance_top_n_by_gain():
    model, X, feature_names = _train_simple_model()
    analyzer = FeatureImportanceAnalyzer()
    report = analyzer.generate(
        model, feature_names, X,
        horizon=3, feature_set_version="feature_set_v1",
    )
    top = report.top_n_by_gain(1)
    assert len(top) == 1
    assert top[0] in feature_names


def test_feature_importance_shap_flag():
    model, X, feature_names = _train_simple_model()
    analyzer = FeatureImportanceAnalyzer()
    report = analyzer.generate(
        model, feature_names, X,
        horizon=3, feature_set_version="feature_set_v1",
    )
    # shap_available flag must be a bool regardless of SHAP installation
    assert isinstance(report.shap_available, bool)


def test_feature_importance_persist(tmp_path):
    model, X, feature_names = _train_simple_model()
    analyzer = FeatureImportanceAnalyzer()
    import os
    path = str(tmp_path / "importance.json")
    report = analyzer.generate(
        model, feature_names, X,
        horizon=3, feature_set_version="feature_set_v1",
        importance_path=path,
    )
    assert os.path.isfile(path)
