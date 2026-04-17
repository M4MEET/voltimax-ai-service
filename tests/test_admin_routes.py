from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.config as cfg_module
from app.config import (
    AppConfig,
    JwtConfig,
    LlmProviderConfig,
    ShopwareConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DASHBOARD_KEY = "test-api-key"


def _make_config(**kwargs) -> AppConfig:
    return AppConfig(
        shopware=ShopwareConfig(
            server_a_url="http://localhost",
            api_key=DASHBOARD_KEY,
        ),
        jwt=JwtConfig(secret="test-secret-that-is-long-enough-32c"),
        llm_providers={
            "openai": LlmProviderConfig(api_key="sk-test", default_model="gpt-4o"),
        },
        **kwargs,
    )


def _make_test_client() -> TestClient:
    """Build a minimal FastAPI app that includes only the admin router."""
    from app.api.routes.admin import router

    test_app = FastAPI()
    test_app.include_router(router)
    return TestClient(test_app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_llm_config_returns_dict():
    """GET /api/admin/config/llm — when admin_config has no stored value, falls
    back to config.yaml data and returns a dict with masked keys."""
    config = _make_config()
    cfg_module._config = config

    try:
        # Mock get_admin_config to return None (triggers config.yaml fallback)
        with patch(
            "app.api.routes.admin.get_admin_config",
            new=AsyncMock(return_value=None),
        ):
            client = _make_test_client()
            response = client.get(
                "/api/admin/config/llm",
                headers={"X-Dashboard-Key": DASHBOARD_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # api_key should be masked in GET responses
        for entry in data.values():
            assert entry.get("api_key") == "***"
    finally:
        cfg_module._config = None


def test_update_topics_returns_ok():
    """PUT /api/admin/topics — saves topic cards and routing, returns ok=True."""
    config = _make_config()
    cfg_module._config = config

    mock_set = AsyncMock()

    try:
        with patch(
            "app.api.routes.admin.set_admin_config",
            new=mock_set,
        ):
            client = _make_test_client()
            cards = [
                {
                    "id": "orders",
                    "title": "Orders",
                    "llm_provider": "openai",
                    "sub_cards": [],
                }
            ]
            response = client.put(
                "/api/admin/topics",
                json=cards,
                headers={"X-Dashboard-Key": DASHBOARD_KEY},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        # set_admin_config should have been called twice (topic_cards + topic_routing)
        assert mock_set.call_count == 2
    finally:
        cfg_module._config = None


def test_auth_rejection_without_key():
    """Requests without X-Dashboard-Key header should be rejected with 401."""
    config = _make_config()
    cfg_module._config = config

    try:
        with patch(
            "app.api.routes.admin.get_admin_config",
            new=AsyncMock(return_value=None),
        ):
            client = _make_test_client()
            response = client.get("/api/admin/config/llm")  # no auth header

        assert response.status_code == 401
    finally:
        cfg_module._config = None


def test_auth_rejection_wrong_key():
    """Requests with a wrong X-Dashboard-Key should be rejected with 401."""
    config = _make_config()
    cfg_module._config = config

    try:
        with patch(
            "app.api.routes.admin.get_admin_config",
            new=AsyncMock(return_value=None),
        ):
            client = _make_test_client()
            response = client.get(
                "/api/admin/config/llm",
                headers={"X-Dashboard-Key": "wrong-key"},
            )

        assert response.status_code == 401
    finally:
        cfg_module._config = None


def test_gdpr_delete_returns_deleted_sessions():
    """DELETE /api/admin/customers/{email}/data — deletes sessions/messages/events,
    returns deleted_sessions count."""
    config = _make_config()
    cfg_module._config = config

    mock_sessions = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[{"id": "s1"}, {"id": "s2"}])
    mock_sessions.return_value.find.return_value = mock_cursor
    mock_sessions.return_value.delete_many = AsyncMock()

    mock_messages = MagicMock()
    mock_messages.return_value.delete_many = AsyncMock()

    mock_events = MagicMock()
    mock_events.return_value.delete_many = AsyncMock()

    try:
        with (
            patch("app.db.collections.sessions_collection", mock_sessions),
            patch("app.db.collections.messages_collection", mock_messages),
            patch("app.db.collections.analytics_events_collection", mock_events),
        ):
            client = _make_test_client()
            response = client.delete(
                "/api/admin/customers/test@example.com/data",
                headers={"X-Dashboard-Key": DASHBOARD_KEY},
            )

        assert response.status_code == 200
        body = response.json()
        assert "deleted_sessions" in body
        assert body["deleted_sessions"] == 2
    finally:
        cfg_module._config = None
