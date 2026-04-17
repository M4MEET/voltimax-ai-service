import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_purge_old_sessions_deletes_old_data():
    mock_sessions = MagicMock()
    mock_sessions.find.return_value.to_list = AsyncMock(return_value=[{"id": "s1"}, {"id": "s2"}])
    mock_sessions.delete_many = AsyncMock(return_value=MagicMock(deleted_count=2))

    mock_messages = MagicMock()
    mock_messages.delete_many = AsyncMock()

    mock_events = MagicMock()
    mock_events.delete_many = AsyncMock()

    with (
        patch("app.tasks.purge.sessions_collection", return_value=mock_sessions),
        patch("app.tasks.purge.messages_collection", return_value=mock_messages),
        patch("app.tasks.purge.analytics_events_collection", return_value=mock_events),
    ):
        from app.tasks.purge import purge_old_sessions
        count = await purge_old_sessions()

    assert count == 2
    mock_messages.delete_many.assert_called_once()
    mock_events.delete_many.assert_called_once()


@pytest.mark.asyncio
async def test_purge_skips_when_retention_zero():
    from unittest.mock import patch
    from app.config import AppConfig, ShopwareConfig, JwtConfig, AnalyticsConfig
    cfg = AppConfig(
        shopware=ShopwareConfig(server_a_url="http://x", api_key="k"),
        jwt=JwtConfig(secret="s"),
        analytics=AnalyticsConfig(retention_days=0),
    )
    with patch("app.tasks.purge.get_config", return_value=cfg):
        from app.tasks.purge import purge_old_sessions
        count = await purge_old_sessions()
    assert count == 0
