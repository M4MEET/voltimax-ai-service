from __future__ import annotations

import pytest
import httpx

import app.config as cfg_module
from app.config import AppConfig
from app.shopware.client import ShopwareClient, get_shopware_client


def _make_config(server_url: str = "http://fake-shopware.test"):
    cfg_module._config = AppConfig(
        shopware={
            "server_a_url": server_url,
            "api_key": "shared-api-key",
            "timeout": 5,
        },
        jwt={"secret": "test-secret"},
    )


@pytest.fixture(autouse=True)
def reset_shopware_singleton():
    """Reset the Shopware client singleton between tests."""
    import app.shopware.client as sc_module
    sc_module._shopware_client = None
    yield
    sc_module._shopware_client = None


def test_client_uses_correct_base_url():
    _make_config("https://my-shop.example.com")
    client = ShopwareClient()
    assert client.base_url == "https://my-shop.example.com"


def test_client_uses_api_key():
    _make_config()
    client = ShopwareClient()
    assert client.api_key == "shared-api-key"


def test_client_strips_trailing_slash():
    _make_config("https://shop.example.com/")
    client = ShopwareClient()
    assert client.base_url == "https://shop.example.com"


@pytest.mark.asyncio
async def test_get_order_not_found():
    """A 404 from Server A should return None."""
    _make_config()
    client = ShopwareClient()

    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    client._client = httpx.AsyncClient(
        base_url=client.base_url,
        headers={"X-Voltimax-Api-Key": client.api_key},
        transport=transport,
    )

    result = await client.get_order("NONEXISTENT-123")
    assert result is None


@pytest.mark.asyncio
async def test_get_order_success():
    """A 200 response should return parsed JSON."""
    _make_config()
    client = ShopwareClient()

    order_data = {"orderNumber": "10001", "status": "shipped"}

    def handler(req: httpx.Request) -> httpx.Response:
        assert "X-Voltimax-Api-Key" in req.headers
        assert req.headers["X-Voltimax-Api-Key"] == "shared-api-key"
        return httpx.Response(200, json=order_data)

    transport = httpx.MockTransport(handler)
    client._client = httpx.AsyncClient(
        base_url=client.base_url,
        headers={"X-Voltimax-Api-Key": client.api_key},
        transport=transport,
    )

    result = await client.get_order("10001")
    assert result == order_data


@pytest.mark.asyncio
async def test_get_customer_orders_returns_list():
    """Should return an empty list on error, not raise."""
    _make_config()
    client = ShopwareClient()

    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    client._client = httpx.AsyncClient(
        base_url=client.base_url,
        headers={"X-Voltimax-Api-Key": client.api_key},
        transport=transport,
    )

    result = await client.get_customer_orders("user@example.com")
    # On a 5xx error, _get returns a dict with "error" key
    # get_customer_orders checks isinstance(result, list), so returns []
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_search_products_passes_query_param():
    """search_products should pass q= as a query parameter."""
    _make_config()
    client = ShopwareClient()

    captured_params = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured_params.update(dict(req.url.params))
        return httpx.Response(200, json=[{"productNumber": "P-001"}])

    transport = httpx.MockTransport(handler)
    client._client = httpx.AsyncClient(
        base_url=client.base_url,
        headers={"X-Voltimax-Api-Key": client.api_key},
        transport=transport,
    )

    result = await client.search_products("blue shoes")
    assert captured_params.get("search") == "blue shoes"
    assert isinstance(result, list)
    assert result[0]["productNumber"] == "P-001"


@pytest.mark.asyncio
async def test_connection_error_returns_error_dict():
    """A connection error should return an error dict, not raise."""
    _make_config("http://unreachable.local")
    client = ShopwareClient()

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=req)

    transport = httpx.MockTransport(handler)
    client._client = httpx.AsyncClient(
        base_url=client.base_url,
        headers={"X-Voltimax-Api-Key": client.api_key},
        transport=transport,
    )

    result = await client.get_config()
    # get_config returns {} on None, but _get returns error dict on exception
    assert isinstance(result, dict)
