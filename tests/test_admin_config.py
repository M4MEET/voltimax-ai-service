import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_get_admin_config_returns_none_when_missing():
    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value=None)
    with patch("app.db.admin_config.admin_config_collection", return_value=mock_coll):
        from app.db.admin_config import get_admin_config
        result = await get_admin_config("llm_providers")
    assert result is None


@pytest.mark.asyncio
async def test_get_admin_config_returns_data():
    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value={"data": {"openai": {"api_key": "sk-test"}}})
    with patch("app.db.admin_config.admin_config_collection", return_value=mock_coll):
        from app.db.admin_config import get_admin_config
        result = await get_admin_config("llm_providers")
    assert result == {"openai": {"api_key": "sk-test"}}


@pytest.mark.asyncio
async def test_set_admin_config_upserts():
    mock_coll = MagicMock()
    mock_coll.update_one = AsyncMock()
    with patch("app.db.admin_config.admin_config_collection", return_value=mock_coll):
        from app.db.admin_config import set_admin_config
        await set_admin_config("llm_providers", {"openai": {}})
    mock_coll.update_one.assert_called_once()
    call_args = mock_coll.update_one.call_args
    assert call_args[0][0] == {"type": "llm_providers"}
    assert call_args[1].get("upsert") is True
