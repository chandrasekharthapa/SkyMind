"""Retired live MCP smoke test.

This module used to launch Puppeteer against Google Flights during ordinary test
collection and then accepted any dictionary containing ``data`` as success. That
made CI network-dependent and could report a tagged transport failure as green.
The same boundary is now covered without a live search by ``test_mcp_interop``:
it initializes and lists the checked-in stdio server, exercises the official SDK
against local provider stubs, distinguishes empty data from provider failure, and
checks cancellation cleanup.
"""

import pytest


pytestmark = pytest.mark.skip(
    reason=(
        "live provider calls are intentionally excluded from automated tests; "
        "use the local-stub MCP interoperability tests"
    )
)


def test_live_provider_probe_is_not_part_of_ci():
    """Keep the historical module importable while making its retirement explicit."""
