import asyncio
import os
import pytest
from backend.services.mcp_client import mcp_gateway
from backend.services.flight_data_service import flight_data_service

@pytest.mark.asyncio
async def test_real_fli_mcp_call():
    """Attempt a real call to fli-mcp. If the executable is missing or the call fails,
    the test will be skipped rather than cause a failure, ensuring CI stability.
    """
    # Ensure the fli-mcp executable exists
    from services.mcp_client import _executable
    if not os.path.isfile(_executable):
        pytest.skip(f"fli-mcp executable not found at {_executable}")
    async with mcp_gateway() as client:
        # Use a benign request that should always succeed (e.g., a future date with a common route)
        result = await flight_data_service.search_flights(
            origin="DEL",
            destination="BOM",
            target_date="2099-01-01",
            session=client,
        )
        # The result must be a dict with a 'data' key (which may be empty if no flights are available)
        assert isinstance(result, dict)
        assert "data" in result
        # If data is empty, that's acceptable; the important part is that the call succeeded without raising.
