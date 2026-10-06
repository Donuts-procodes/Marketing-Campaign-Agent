import json
import pytest
from unittest.mock import AsyncMock, patch

from orchestrator.core.storage import Storage
from orchestrator.services.campaign_service import CampaignService


@pytest.mark.asyncio
async def test_storage_redis_event_append_and_load():
    from unittest.mock import MagicMock

    storage = Storage()
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock()

    mock_redis.pipeline.return_value = mock_pipe
    mock_redis.lrange = AsyncMock()
    storage.redis = mock_redis

    test_event = {"seq": 1, "type": "STEP_START", "message": "Starting research"}
    await storage.append_event("job-test-123", test_event)

    mock_pipe.rpush.assert_called_once()
    mock_pipe.expire.assert_called_once()
    mock_pipe.execute.assert_awaited_once()

    # Test load_events
    mock_redis.lrange.return_value = [json.dumps(test_event).encode("utf-8")]
    loaded = await storage.load_events("job-test-123")
    assert len(loaded) == 1
    assert loaded[0]["seq"] == 1
    assert loaded[0]["type"] == "STEP_START"


@pytest.mark.asyncio
async def test_campaign_service_stream_events_replays_from_redis():
    service = CampaignService()
    job_id = "job-redis-replay-456"

    # Make sure job is NOT in memory
    if job_id in service._jobs:
        del service._jobs[job_id]

    events = [
        {"seq": 1, "type": "STEP_START", "message": "Init"},
        {"seq": 2, "type": "RESEARCH_UPDATE", "message": "Discovered competitors"},
    ]

    mock_storage = AsyncMock()
    mock_storage.load_events.return_value = events

    with patch("orchestrator.services.campaign_service.get_storage", return_value=mock_storage):
        frames = []
        async for frame in service.stream_job_events(job_id, after_seq=0):
            frames.append(frame)

        assert len(frames) == 2
        assert 'id: 1' in frames[0]
        assert 'id: 2' in frames[1]
        assert '"seq": 1' in frames[0]
        assert '"seq": 2' in frames[1]

        mock_storage.load_events.assert_awaited_once_with(job_id)
