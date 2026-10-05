"""Global pytest fixtures for SkyMind backend tests.

Provides automatic test isolation for singleton services that maintain
in-memory state (caches, counters, pending task queues) between test runs.
"""

import os

import pytest

# The app fetches trained models from Supabase Storage at startup; tests must
# not reach out to a real bucket.
os.environ.setdefault("MODEL_SYNC_ON_START", "0")
# Training tests fit real XGBoost models; a 25-trial Optuna search per horizon
# would make them minutes long. Tests that cover tuning pass n_trials directly.
os.environ.setdefault("MODEL_TUNING_TRIALS", "0")


@pytest.fixture(autouse=True)
def clear_market_snapshot_cache():
    """Clear the MarketSnapshotProvider singleton cache before every test.

    The default MarketSnapshotProvider is a module-level singleton with a
    TTL-based in-memory cache. Without clearing it between tests, the first
    test to run (e.g. test_prediction_service_orchestration at 8500.0) will
    poison the cache for subsequent tests that mock different prices.

    This fixture runs automatically for every test without needing to be
    explicitly declared in individual test functions.
    """
    try:
        from backend.services.market_snapshot_provider import market_snapshot_provider
        market_snapshot_provider._cache.clear()
        market_snapshot_provider._pending_tasks.clear()
    except Exception:
        # If the import fails or attributes don't exist, silently skip —
        # this fixture must never cause an unrelated test to fail.
        pass

    yield

    # Also clear after each test to ensure no residue
    try:
        from backend.services.market_snapshot_provider import market_snapshot_provider
        market_snapshot_provider._cache.clear()
        market_snapshot_provider._pending_tasks.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def reset_firewall_client():
    """Prevent one test's injected hosted-guardrail client leaking into another."""
    from backend.firewall.client import NVIDIAClientProvider

    NVIDIAClientProvider.reset_client()
    yield
    NVIDIAClientProvider.reset_client()



@pytest.fixture(autouse=True)
def _fresh_chat_search_cache():
    """Chat tools reuse live results for 10 minutes; tests must not see each
    other's mocked results."""
    from backend.services.chatbot_tools import clear_search_cache
    clear_search_cache()
    yield
    clear_search_cache()
