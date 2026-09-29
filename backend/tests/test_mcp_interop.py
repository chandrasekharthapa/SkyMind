import json
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from mcp import ClientSession
# mcp SDK v2 renamed McpError -> MCPError (mcp==2.2.0); alias to the old name.
from mcp.shared.exceptions import MCPError as McpError
from mcp.client.stdio import stdio_client
from backend.services import mcp_client
from backend.services.mcp_client import mcp_gateway


SECRET_ENV_NAMES = (
    "SUPABASE_SERVICE_KEY",
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "RAZORPAY_KEY_SECRET",
)


pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is required for the checked-in MCP stdio server",
)


@pytest.mark.asyncio
async def test_mcp_initializes_and_lists_only_real_tool():
    """Exercise Python-to-Node discovery without calling the live provider."""
    async with mcp_gateway() as client:
        tools = (await client.list_tools()).tools

    assert [tool.name for tool in tools] == ["search_flights"]
    schema = tools[0].input_schema
    assert schema["required"] == ["from", "to", "departDate"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "from", "to", "departDate", "returnDate", "adults",
        "children", "infants", "cabin_class", "max_results",
    }


def test_child_environment_is_allowlisted_and_built_at_call_time(monkeypatch):
    for name in SECRET_ENV_NAMES:
        monkeypatch.setenv(name, f"should-not-cross-{name.lower()}")
    monkeypatch.setenv("PROXY_SERVER", "http://first-proxy.invalid")
    monkeypatch.setenv("GOOGLE_FLIGHTS_PROVIDER_MODULE", "/tmp/provider-one.js")

    first = mcp_client._server_parameters()

    monkeypatch.setenv("PROXY_SERVER", "http://second-proxy.invalid")
    monkeypatch.setenv("GOOGLE_FLIGHTS_PROVIDER_MODULE", "/tmp/provider-two.js")
    second = mcp_client._server_parameters()

    first_env = first.env or {}
    second_env = second.env or {}
    assert first_env["PROXY_SERVER"] == "http://first-proxy.invalid"
    assert second_env["PROXY_SERVER"] == "http://second-proxy.invalid"
    assert first_env["GOOGLE_FLIGHTS_PROVIDER_MODULE"] == "/tmp/provider-one.js"
    assert second_env["GOOGLE_FLIGHTS_PROVIDER_MODULE"] == "/tmp/provider-two.js"
    assert all(name not in second_env for name in SECRET_ENV_NAMES)
    assert set(second_env).issubset(set(mcp_client._PROVIDER_ENV_VARS))


@pytest.mark.asyncio
async def test_gateway_closes_transport_when_call_is_cancelled(monkeypatch):
    """Cancellation must unwind both SDK and child-transport contexts."""
    events = []

    @asynccontextmanager
    async def fake_stdio(params):
        events.append(("transport_enter", params.command))
        try:
            yield (object(), object())
        finally:
            events.append("transport_exit")

    class FakeSession:
        def __init__(self, read_stream, write_stream):
            events.append("session_init")

        async def __aenter__(self):
            events.append("session_enter")
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            events.append(("session_exit", exc_type))

        async def initialize(self):
            events.append("initialize")

        async def call_tool(self, name, arguments):
            import asyncio

            events.append("call_started")
            await asyncio.Event().wait()

    monkeypatch.setattr(mcp_client, "stdio_client", fake_stdio)
    monkeypatch.setattr(mcp_client, "ClientSession", FakeSession)

    import asyncio

    task = asyncio.create_task(_cancelled_gateway_call())
    while "call_started" not in events:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert events[-2][0] == "session_exit"
    assert events[-2][1] is asyncio.CancelledError
    assert events[-1] == "transport_exit"


async def _cancelled_gateway_call():
    async with mcp_gateway() as client:
        await client.call_tool(
            "search_flights",
            {"from": "DEL", "to": "BOM", "departDate": "2099-01-01"},
        )


async def _timed_fresh_search():
    from backend.services.flight_data_service import FlightDataService

    return await FlightDataService().search_flights(
        "DEL", "BOM", "2099-01-01"
    )


@pytest.mark.asyncio
async def test_fresh_search_timeout_cancels_gateway_and_unwinds_transport(
    monkeypatch
):
    """The service deadline covers startup, call, and child teardown."""
    import asyncio

    events = []

    @asynccontextmanager
    async def fake_stdio(params):
        events.append("transport_enter")
        try:
            yield (object(), object())
        finally:
            events.append("transport_exit")

    class HangingSession:
        def __init__(self, read_stream, write_stream):
            pass

        async def __aenter__(self):
            events.append("session_enter")
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            events.append(("session_exit", exc_type))

        async def initialize(self):
            events.append("initialize")

        async def call_tool(self, name, arguments):
            events.append("call_started")
            await asyncio.Event().wait()

    monkeypatch.setattr(mcp_client, "stdio_client", fake_stdio)
    monkeypatch.setattr(mcp_client, "ClientSession", HangingSession)
    monkeypatch.setenv("MCP_TIMEOUT", "0.01")
    monkeypatch.setenv("MCP_MAX_RETRIES", "1")

    result = await _timed_fresh_search()

    assert result["status"] == "error"
    assert result["error_kind"] == "timeout"
    assert result["attempts"] == 1
    assert events[-2][0] == "session_exit"
    assert events[-2][1] is asyncio.CancelledError
    assert events[-1] == "transport_exit"


async def _exchange_node(lines, env=None):
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "node",
        mcp_client._script_path,
        cwd=str(Path(mcp_client._script_path).parent),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    payload = "".join(json.dumps(line) + "\n" for line in lines).encode()
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(payload), timeout=10
        )
    except BaseException:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise
    assert proc.returncode == 0, stderr.decode(errors="replace")
    return [json.loads(line) for line in stdout.decode().splitlines()]


@pytest.mark.asyncio
async def test_mcp_rejects_missing_search_identity_without_loading_browser():
    responses = await _exchange_node([
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "search_flights", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_flights",
                "arguments": {
                    "from": "DEL",
                    "to": "BOM",
                    "departDate": "2026-02-31",
                },
            },
        },
    ])

    assert [response["error"]["code"] for response in responses] == [
        -32602,
        -32602,
    ]


@pytest.mark.asyncio
async def test_mcp_rejects_unknown_argument_key_without_loading_browser():
    responses = await _exchange_node([{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_flights",
            "arguments": {
                "from": "DEL",
                "to": "BOM",
                "departDate": "2099-01-01",
                "unexpected": True,
            },
        },
    }])

    assert responses[0]["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_mcp_returns_protocol_errors_instead_of_hanging():
    responses = await _exchange_node([
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 1, "method": "unknown/method"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "unknown_tool", "arguments": {}},
        },
    ])

    # The notification emits no response. An unknown JSON-RPC method is a
    # protocol error; an unknown tool is a tools/call application error.
    assert len(responses) == 2
    assert responses[0]["error"]["code"] == -32601
    assert responses[1]["result"]["isError"] is True
    assert "Tool not found" in responses[1]["result"]["content"][0]["text"]


async def _call_stub_provider(tmp_path, provider_body, arguments):
    provider = tmp_path / "provider.js"
    provider.write_text(provider_body, encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("GOOGLE_FLIGHTS_PROVIDER_MODULE", str(provider))
    try:
        params = mcp_client._server_parameters()
        async with stdio_client(params) as transport:
            async with ClientSession(transport[0], transport[1]) as client:
                await client.initialize()
                return await client.call_tool("search_flights", arguments)
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_sdk_surfaces_invalid_params_as_mcp_error(tmp_path):
    with pytest.raises(McpError) as caught:
        await _call_stub_provider(
            tmp_path,
            "module.exports = class StubProvider {};",
            {
                "from": "DEL",
                "to": "BOM",
                "departDate": "2099-01-01",
                "unexpected": True,
            },
        )

    assert caught.value.error.code == -32602


@pytest.mark.asyncio
async def test_valid_sdk_call_forwards_complete_request_and_preserves_empty(tmp_path):
    """Exercise the official SDK, Node boundary, and a local provider stub."""
    capture = tmp_path / "captured.json"
    provider_body = f"""
const fs = require('fs');
module.exports = class StubProvider {{
  async searchFlights(...args) {{
    fs.writeFileSync({json.dumps(str(capture))}, JSON.stringify(args));
    return [];
  }}
}};
"""
    arguments = {
        "from": "DEL",
        "to": "BOM",
        "departDate": "2099-01-01",
        "returnDate": "2099-01-08",
        "adults": 2,
        "children": 1,
        "infants": 1,
        "cabin_class": "business",
        "max_results": 7,
    }

    result = await _call_stub_provider(tmp_path, provider_body, arguments)

    assert result.isError is False
    assert json.loads(result.content[0].text) == []
    assert json.loads(capture.read_text(encoding="utf-8")) == [
        "DEL", "BOM", "2099-01-01", "2099-01-08",
        {"adults": 2, "children": 1, "infants": 1},
        "business",
    ]


@pytest.mark.asyncio
async def test_malformed_provider_result_is_a_tool_error(tmp_path):
    result = await _call_stub_provider(
        tmp_path,
        "module.exports = class StubProvider { async searchFlights() { return {}; } };",
        {"from": "DEL", "to": "BOM", "departDate": "2099-01-01"},
    )

    assert result.isError is True
    assert "invalid result" in result.content[0].text


@pytest.mark.asyncio
async def test_valid_sdk_call_distinguishes_provider_failure(tmp_path):
    provider_body = """
module.exports = class StubProvider {
  async searchFlights() { return { error: 'stub crawl failed' }; }
};
"""
    result = await _call_stub_provider(
        tmp_path,
        provider_body,
        {"from": "DEL", "to": "BOM", "departDate": "2099-01-01"},
    )

    assert result.isError is True
    assert "stub crawl failed" in result.content[0].text
