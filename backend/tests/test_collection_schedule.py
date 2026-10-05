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


# ── Model publishing: every horizon goes up, and the server pulls it down ──

class _FakeBucket:
    def __init__(self, files=None):
        self.files = dict(files or {})

    def upload(self, path, file, file_options=None):
        self.files[path] = file

    def download(self, name):
        return self.files[name]

    def list(self):
        return [{"name": n} for n in self.files] + [{"name": "notes.txt"}]


def _db_with(bucket):
    from backend.database.database import Database
    db = Database.__new__(Database)
    db.supabase = MagicMock()
    db.supabase.storage.from_.return_value = bucket
    return db


def test_bundle_upload_sends_every_horizon_and_its_metadata(tmp_path):
    for name in ("fare_forecast_1d.pkl", "fare_forecast_1d.metadata.json",
                 "fare_forecast_3d.pkl", "fare_forecast_3d.metadata.json", "global_model.pkl", "scratch.tmp"):
        (tmp_path / name).write_bytes(b"x")
    bucket = _FakeBucket()
    uploaded = _db_with(bucket).upload_model_bundle(str(tmp_path))
    assert uploaded == sorted(bucket.files) and "scratch.tmp" not in bucket.files
    assert {"fare_forecast_3d.pkl", "fare_forecast_3d.metadata.json"} <= set(bucket.files)


def test_bundle_download_writes_model_files_only(tmp_path):
    bucket = _FakeBucket({"fare_forecast_1d.pkl": b"m", "fare_forecast_1d.metadata.json": b"{}"})
    written = _db_with(bucket).download_model_bundle(str(tmp_path))
    assert written == ["fare_forecast_1d.metadata.json", "fare_forecast_1d.pkl"]
    assert not (tmp_path / "notes.txt").exists()


def test_a_trained_run_publishes_the_bundle():
    import backend.run_pipeline as rp
    predictor = MagicMock()
    predictor.train.return_value = {"trained": True, "trained_horizons": [1]}
    db = MagicMock()
    db.upload_model_bundle.return_value = ["fare_forecast_1d.pkl"]
    with patch("backend.ml.price_model.get_predictor", return_value=predictor), \
         patch("os.path.exists", return_value=True), \
         patch("backend.database.database.database", db):
        assert rp.run_retraining() is True
    db.upload_model_bundle.assert_called_once()


def test_server_sync_loads_what_it_downloaded_and_survives_storage_errors():
    import backend.main as main
    predictor = MagicMock()
    with patch("backend.database.database.database") as db, \
         patch.object(main, "get_predictor", return_value=predictor):
        db.download_model_bundle.return_value = ["fare_forecast_1d.pkl"]
        main._sync_models_from_storage()
        predictor.load.assert_called_once()
        db.download_model_bundle.side_effect = RuntimeError("bucket not found")
        main._sync_models_from_storage()   # logs, does not raise
