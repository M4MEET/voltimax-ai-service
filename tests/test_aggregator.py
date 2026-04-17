import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_performance_returns_structure():
    mock_coll = MagicMock()

    async def fake_to_list(n):
        return []

    class FakeCursor:
        async def to_list(self, n):
            return []

    mock_coll.aggregate = MagicMock(return_value=FakeCursor())

    with patch("app.analytics.aggregator.analytics_events_collection", return_value=mock_coll):
        from app.analytics.aggregator import AnalyticsAggregator
        agg = AnalyticsAggregator()
        result = await agg.get_performance(7)

    assert "avg_response_ms" in result
    assert "avg_chat_duration_s" in result
    assert "by_provider" in result
    assert result["period_days"] == 7
    assert isinstance(result["by_provider"], list)
