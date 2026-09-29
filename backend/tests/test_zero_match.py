import pytest
from contextlib import asynccontextmanager

# mcp SDK v2 renamed McpError -> MCPError (mcp==2.2.0); alias to the old name.
from mcp.shared.exceptions import MCPError as McpError
from mcp.types import INVALID_PARAMS, ErrorData


def _invalid_params_error(message: str = "invalid parameters") -> McpError:
    """Build an INVALID_PARAMS error across mcp SDK v1 and v2.

    v2 flattened the constructor to ``MCPError(code, message)``; v1 took a
    single ``ErrorData``. Try the v2 shape first and fall back, so the raise
    itself never becomes the ``TypeError`` the service would then misreport as
    an "unexpected" failure instead of an "input" one.
    """
    try:
        return McpError(INVALID_PARAMS, message)
    except TypeError:
        return McpError(ErrorData(code=INVALID_PARAMS, message=message))

from backend.services import flight_data_service as flight_module
from backend.services.flight_data_service import (
    FlightDataService,
    STATUS_EMPTY,
    STATUS_ERROR,
    STATUS_OK,
)


class _EmptyMcpSession:
    def __init__(self, result=None):
        self.calls = []
        self.result = {"data": []} if result is None else result

    async def call_tool(self, name, payload):
        self.calls.append((name, payload))
        return self.result


@pytest.mark.asyncio
async def test_zero_match_returns_empty_without_synthetic_fallback():
    """A provider's empty result remains an explicitly empty answer."""
    session = _EmptyMcpSession()

    result = await FlightDataService().search_flights(
        origin="AAA",
        destination="BBB",
        target_date="2099-01-01",
        session=session,
    )

    assert result["status"] == STATUS_EMPTY
    assert result["data"] == []
    assert session.calls == [(
        "search_flights",
        {
            "from": "AAA",
            "to": "BBB",
            "departDate": "2099-01-01",
            "returnDate": None,
            "adults": 1,
            "children": 0,
            "infants": 0,
            "cabin_class": "economy",
            "max_results": 20,
        },
    )]


@pytest.mark.asyncio
async def test_default_provider_timeout_exceeds_browser_navigation(monkeypatch):
    """The outer call budget must not pre-empt the provider's 60-second bound."""
    observed = {}

    async def slow_result():
        return {"data": []}

    class _Session:
        def call_tool(self, name, payload):
            return slow_result()

    async def fake_wait_for(awaitable, timeout):
        observed["timeout"] = timeout
        return await awaitable

    monkeypatch.delenv("MCP_TIMEOUT", raising=False)
    monkeypatch.setattr(flight_module.asyncio, "wait_for", fake_wait_for)

    result = await FlightDataService().search_flights(
        "DEL", "BOM", "2099-01-01", session=_Session()
    )

    assert result["status"] == STATUS_EMPTY
    assert observed["timeout"] == 90.0


@pytest.mark.asyncio
async def test_fresh_gateway_uses_canonical_search_schema(monkeypatch):
    """The production-created MCP session must receive the advertised schema."""
    session = _EmptyMcpSession()

    @asynccontextmanager
    async def fake_gateway():
        yield session

    from backend.services import mcp_client

    monkeypatch.setattr(mcp_client, "mcp_gateway", fake_gateway)

    result = await FlightDataService().search_flights(
        origin=" del ",
        destination="bom",
        target_date="2099-01-01",
        children=1,
        infants=1,
        return_date="2099-01-08",
    )

    assert result["status"] == STATUS_EMPTY
    assert session.calls == [(
        "search_flights",
        {
            "from": "DEL",
            "to": "BOM",
            "departDate": "2099-01-01",
            "returnDate": "2099-01-08",
            "adults": 1,
            "children": 1,
            "infants": 1,
            "cabin_class": "economy",
            "max_results": 20,
        },
    )]


@pytest.mark.asyncio
async def test_max_results_is_enforced_even_if_provider_over_returns():
    session = _EmptyMcpSession({
        "data": [
            {"price": 1000 + i, "currency": "INR"}
            for i in range(5)
        ]
    })

    result = await FlightDataService().search_flights(
        "DEL", "BOM", "2099-01-01", max_results=2, session=session
    )

    assert result["status"] == STATUS_OK
    assert len(result["data"]) == 2


@pytest.mark.asyncio
async def test_provider_tool_error_is_not_reported_as_empty(monkeypatch):
    monkeypatch.setenv("MCP_MAX_RETRIES", "1")
    session = _EmptyMcpSession({
        "isError": True,
        "content": [{"type": "text", "text": "stub crawl failed"}],
    })

    result = await FlightDataService().search_flights(
        "DEL", "BOM", "2099-01-01", session=session
    )

    assert result["status"] == STATUS_ERROR
    assert result["error_kind"] == "provider"
    assert "stub crawl failed" in result["error"]


@pytest.mark.asyncio
async def test_invalid_params_error_is_not_retried(monkeypatch):
    monkeypatch.setenv("MCP_MAX_RETRIES", "3")

    class _InvalidSession:
        def __init__(self):
            self.calls = 0

        async def call_tool(self, name, payload):
            self.calls += 1
            raise _invalid_params_error()

    session = _InvalidSession()
    result = await FlightDataService().search_flights(
        "DEL", "BOM", "2099-01-01", session=session
    )

    assert result["status"] == STATUS_ERROR
    assert result["error_kind"] == "input"
    assert result["attempts"] == 1
    assert session.calls == 1


@pytest.mark.asyncio
async def test_fresh_timeout_wraps_gateway_lifecycle(monkeypatch):
    events = []

    @asynccontextmanager
    async def fake_gateway():
        events.append("enter")
        try:
            yield _EmptyMcpSession()
        finally:
            events.append("exit")

    async def fake_wait_for(awaitable, timeout):
        events.append(("wait_for", timeout))
        result = await awaitable
        events.append("wait_done")
        return result

    from backend.services import mcp_client

    monkeypatch.delenv("MCP_TIMEOUT", raising=False)
    monkeypatch.setattr(mcp_client, "mcp_gateway", fake_gateway)
    monkeypatch.setattr(flight_module.asyncio, "wait_for", fake_wait_for)

    result = await FlightDataService().search_flights(
        "DEL", "BOM", "2099-01-01"
    )

    assert result["status"] == STATUS_EMPTY
    assert events == [
        ("wait_for", 90.0), "enter", "exit", "wait_done"
    ]
