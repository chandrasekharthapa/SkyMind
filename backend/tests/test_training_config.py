"""Tests for TrainingConfig."""
import pytest
from backend.ml.training_config import TrainingConfig


def test_training_config_is_immutable():
    cfg = TrainingConfig(feature_set_version="feature_set_v1", forecast_horizon=3)
    with pytest.raises((AttributeError, TypeError)):
        cfg.forecast_horizon = 999  # frozen dataclass


def test_training_config_defaults():
    cfg = TrainingConfig(feature_set_version="feature_set_v1", forecast_horizon=7)
    assert cfg.model_type == "xgboost"
    assert cfg.random_seed == 42
    assert cfg.validation_strategy == "expanding"
    assert cfg.minimum_training_rows > 0
    assert isinstance(cfg.hyperparameters, dict)
    assert "learning_rate" in cfg.hyperparameters


def test_training_config_hash_is_deterministic():
    cfg1 = TrainingConfig(feature_set_version="feature_set_v1", forecast_horizon=3, random_seed=42)
    cfg2 = TrainingConfig(feature_set_version="feature_set_v1", forecast_horizon=3, random_seed=42)
    assert cfg1.config_hash() == cfg2.config_hash()


def test_training_config_hash_differs_on_change():
    cfg1 = TrainingConfig(feature_set_version="feature_set_v1", forecast_horizon=3, random_seed=42)
    cfg2 = TrainingConfig(feature_set_version="feature_set_v1", forecast_horizon=3, random_seed=99)
    assert cfg1.config_hash() != cfg2.config_hash()


def test_training_config_to_dict():
    cfg = TrainingConfig(feature_set_version="legacy", forecast_horizon=1)
    d = cfg.to_dict()
    assert d["feature_set_version"] == "legacy"
    assert d["forecast_horizon"] == 1
    assert "hyperparameters" in d
