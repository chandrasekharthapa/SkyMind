"""The anchored collection schedule and the pipeline's 'not enough history' path."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.route_catalog.route_config import RouteCatalogConfig


def _cfg(schedule):
    cfg = RouteCatalogConfig.__new__(RouteCatalogConfig)
    cfg._raw_config = {"collector": {"departure_schedule": schedule,
                                     "departure_buckets": [1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 75, 90]}}
    cfg.config_source = "test"
    return cfg


ANCHORED = {"mode": "anchored", "daily_window": 7, "anchor_every_days": 13, "max_days": 90}


def _dates(cfg, day):
    return {day + timedelta(days=k) for k in cfg.get_departure_offsets(day)}


def test_anchor_dates_are_searched_again_every_day_until_departure():
    cfg = _cfg(ANCHORED)
    d0 = date(2026, 10, 4)
    far = {d for d in _dates(cfg, d0) if (d - d0).days > 7}
    for n in range(1, 8):
        assert far - {d0 + timedelta(days=90)} <= _dates(cfg, d0 + timedelta(days=n)) | {
            d for d in far if (d - (d0 + timedelta(days=n))).days <= 0}


def test_every_long_range_observation_can_be_labelled_1_3_and_7_days_later():
    cfg = _cfg(ANCHORED)
    d0 = date(2026, 10, 4)
    for dep in _dates(cfg, d0):
        for h in (1, 3, 7):
            later = d0 + timedelta(days=h)
            if (dep - later).days >= 1:
                assert dep in _dates(cfg, later), (dep, h)


def test_anchors_fall_on_different_weekdays_and_cost_stays_flat():
    cfg = _cfg(ANCHORED)
    d0 = date(2026, 10, 4)
    offsets = cfg.get_departure_offsets(d0)
    assert offsets[:7] == list(range(1, 8)) and len(offsets) <= 14
    weekdays = {(d0 + timedelta(days=k)).weekday() for k in offsets[7:]}
    assert len(weekdays) >= 5


def test_buckets_mode_and_bad_config_keep_the_old_offsets():
    assert _cfg({"mode": "buckets"}).get_departure_offsets(date(2026, 10, 4))[:3] == [1, 2, 3]
    assert _cfg(None).get_departure_offsets(date(2026, 10, 4))[-1] == 90


def test_the_shipped_catalogue_uses_the_anchored_schedule():
    from backend.route_catalog import route_catalog_config
    assert route_catalog_config.get_departure_offsets(date(2026, 10, 4))[:7] == list(range(1, 8))


def _run_retraining_with(summary, model_exists=False):
    import backend.run_pipeline as rp
    predictor = MagicMock()
    predictor.train.return_value = summary
    with patch("backend.ml.price_model.get_predictor", return_value=predictor), \
         patch("os.path.exists", return_value=model_exists):
        return rp.run_retraining()


def test_too_little_history_is_a_skip_not_a_failure():
    assert _run_retraining_with({"trained": False, "insufficient_history": True,
                                 "rejected_horizons": {1: "only 0 training row(s)"}}) is True


def test_other_training_refusals_still_fail_the_pipeline():
    assert _run_retraining_with({"trained": False, "insufficient_history": False,
                                 "rejected_horizons": {1: "timeline leakage audit failed"}}) is False
