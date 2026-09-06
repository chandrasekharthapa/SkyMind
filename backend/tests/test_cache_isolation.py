"""Integration Test: Cache Isolation."""

import pytest
from backend.services.market_snapshot_provider import market_snapshot_provider

def test_cache_isolation_keys():
    k1 = market_snapshot_provider._get_cache_key("DEL", "BOM", "2026-07-30")
    k2 = market_snapshot_provider._get_cache_key("DEL", "BBI", "2026-07-30")
    k3 = market_snapshot_provider._get_cache_key("DEL", "BOM", "2026-08-15")

    assert k1 != k2
    assert k1 != k3
    assert k2 != k3
