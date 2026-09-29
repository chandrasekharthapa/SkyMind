import pytest

from backend.services.flight_search_service import flight_search_service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"origin_iata": "DE1"}, "origin_iata"),
        ({"destination_iata": "B0M"}, "destination_iata"),
        ({"destination_iata": "DEL"}, "must differ"),
        ({"departure_date": "2099-02-30"}, "departure_date"),
        ({"return_date": "2098-12-31"}, "return_date"),
        ({"cabin_class": "cargo"}, "cabin_class"),
        ({"adults": True}, "adults"),
        ({"children": -1}, "children"),
        ({"infants": 2}, "infants cannot exceed adults"),
        ({"adults": 5, "children": 5}, "total passengers"),
        ({"max_results": 51}, "max_results"),
    ],
)
async def test_shared_search_validation_rejects_bad_input_before_dependencies(
    kwargs, message
):
    """Every caller reaches the same complete request boundary."""
    call = {
        "origin_iata": "DEL",
        "destination_iata": "BOM",
        "departure_date": "2099-01-01",
    }
    call.update(kwargs)

    with pytest.raises(ValueError, match=message):
        await flight_search_service.search(**call)


@pytest.mark.asyncio
async def test_shared_search_validation_normalizes_identity_before_transport(
    monkeypatch
):
    """Lowercase and surrounding whitespace become the canonical MCP identity."""
    observed = {}

    class StopAfterTransport(Exception):
        pass

    async def capture(**kwargs):
        observed.update(kwargs)
        raise StopAfterTransport

    monkeypatch.setattr(
        "backend.services.flight_search_service.flight_data_service.search_flights",
        capture,
    )

    # The orchestration catches transport failures and proceeds to its cache, so
    # stop that branch too after the normalized request has been captured.
    def stop_cache(*args, **kwargs):
        raise StopAfterTransport

    monkeypatch.setattr(
        flight_search_service.repository,
        "get_price_history_cache",
        stop_cache,
    )
    monkeypatch.setattr(
        flight_search_service.repository,
        "search_airports",
        lambda *args, **kwargs: [],
    )

    await flight_search_service.search(
        origin_iata=" del ",
        destination_iata="bom",
        departure_date="2099-01-01",
        cabin_class=" business ",
    )

    assert observed["origin"] == "DEL"
    assert observed["destination"] == "BOM"
    assert observed["target_date"] == "2099-01-01"
    assert observed["cabin_class"] == "BUSINESS"
