import pytest

from backend.database import database as database_module
from backend.database.database import (
    Database,
    DatabaseConfigurationError,
)


class _FalseyDependency:
    def __bool__(self):
        return False


class _FalseySessionFactory(_FalseyDependency):
    def __init__(self, error=None):
        self.called = False
        self.error = error or RuntimeError("injected session factory used")

    def __call__(self):
        self.called = True
        raise self.error


def _clear_database_environment(monkeypatch):
    for name in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_ANON_KEY",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(database_module, "_engine", None)
    monkeypatch.setattr(database_module, "_SessionLocal", None)


def test_falsey_database_dependencies_preserve_identity():
    service = _FalseyDependency()
    anon = _FalseyDependency()
    sessions = _FalseySessionFactory()

    db = Database(
        supabase_client=service,
        anon_client=anon,
        session_factory=sessions,
    )

    assert db.supabase is service
    assert db.anon is anon
    assert db._session_factory is sessions


def test_falsey_session_factory_is_not_replaced(monkeypatch):
    sessions = _FalseySessionFactory(DatabaseConfigurationError("injected factory"))
    db = Database(
        supabase_client=_FalseyDependency(),
        session_factory=sessions,
    )

    with pytest.raises(DatabaseConfigurationError, match="injected factory"):
        db.get_training_dataset()
    assert sessions.called is True
    assert db.last_load_failed is True


def test_import_safe_database_fails_explicitly_on_first_training_use(monkeypatch):
    _clear_database_environment(monkeypatch)
    db = Database()

    with pytest.raises(DatabaseConfigurationError, match="Missing Supabase"):
        db.get_training_dataset()
    assert db.last_load_failed is True


@pytest.mark.parametrize(
    "operation",
    [
        lambda db: db.get_active_alerts(),
        lambda db: db.search_flights("DEL", "BOM", "2099-01-01"),
        lambda db: db.download_model("unused.pkl"),
    ],
)
def test_missing_supabase_config_is_not_reported_as_empty_success(
    monkeypatch, operation
):
    _clear_database_environment(monkeypatch)
    db = Database()

    with pytest.raises(DatabaseConfigurationError, match="Missing Supabase"):
        operation(db)
