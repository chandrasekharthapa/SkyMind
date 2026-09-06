"""Global pytest fixtures for SkyMind backend tests.

Provides automatic test isolation for singleton services that maintain
in-memory state (caches, counters, pending task queues) between test runs.
"""

import pytest


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
