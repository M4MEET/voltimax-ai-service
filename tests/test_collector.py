import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_track_response_time_stores_event():
    mock_coll = MagicMock()
    mock_coll.insert_one = AsyncMock()
    with patch("app.analytics.collector.analytics_events_collection", return_value=mock_coll):
        from app.analytics.collector import track_response_time
        await track_response_time("sess1", 350, 280, "openai")
    doc = mock_coll.insert_one.call_args[0][0]
    assert doc["event_type"] == "response_time"
    assert doc["response_time_ms"] == 350
    assert doc["llm_latency_ms"] == 280
    assert doc["provider"] == "openai"


@pytest.mark.asyncio
async def test_track_session_end_stores_event():
    mock_coll = MagicMock()
    mock_coll.insert_one = AsyncMock()
    with patch("app.analytics.collector.analytics_events_collection", return_value=mock_coll):
        from app.analytics.collector import track_session_end
        await track_session_end("sess1", 120, 8)
    doc = mock_coll.insert_one.call_args[0][0]
    assert doc["event_type"] == "session_end"
    assert doc["duration_seconds"] == 120
