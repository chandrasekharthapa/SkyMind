import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

load_dotenv()

# Only provider runtime controls cross into the Node child. Passing os.environ
# would also disclose database, mail, payment, and hosted-model credentials that
# the flight scraper neither needs nor should receive.
_PROVIDER_ENV_VARS = (
    "PUPPETEER_EXECUTABLE_PATH",
    # Where Puppeteer looks for the browser `npm ci` downloaded. On Render the
    # build writes Chrome inside the project (the home-directory default does not
    # survive into the running service), and without this variable the child
    # fell back to /opt/render/.cache/puppeteer and failed every search with
    # "Could not find Chrome" even though the build had installed it.
    "PUPPETEER_CACHE_DIR",
    "PUPPETEER_HEADLESS",
    "PROXY_SERVER",
    "PROXY_USERNAME",
    "PROXY_PASSWORD",
    "GOOGLE_FLIGHTS_PROVIDER_MODULE",
    "DEBUG",
)

# Configure the stdio server parameters for the checked-in Node process. Client
# lifetime is deliberately scoped to mcp_gateway(): the previous cached-client
# path had two process-global caches, no public teardown, and no recovery path
# after a stale child process.
_script_path = os.path.abspath(
    os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..", "india-flight-mcp", "src", "mcp", "stdio_server.js",
        )
    )
)
def _server_parameters() -> StdioServerParameters:
    """Build child parameters from the environment at operation time.

    Tests and long-running processes can change provider controls after this
    module is imported. Capturing them in a module-level object made those
    changes ineffective and encouraged callers to restart the backend merely to
    update a proxy or browser path. The allowlist also keeps unrelated database,
    mail, payment, and hosted-model credentials out of the scraper child.
    """
    provider_env = {
        name: value
        for name in _PROVIDER_ENV_VARS
        if (value := os.getenv(name)) is not None
    }
    return StdioServerParameters(
        command="node",
        args=[_script_path],
        cwd=os.path.dirname(_script_path),
        env=provider_env,
    )


@asynccontextmanager
async def mcp_gateway():
    """Yield one initialized MCP session and always close its child process."""
    async with stdio_client(_server_parameters()) as transport:
        async with ClientSession(transport[0], transport[1]) as client:
            await client.initialize()
            yield client
