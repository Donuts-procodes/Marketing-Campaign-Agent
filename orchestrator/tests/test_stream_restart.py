"""After a restart, a finished run whose last event is an approval is not reported as interrupted."""

import asyncio


def test_finished_run_with_later_events_is_not_marked_interrupted(monkeypatch):
    from orchestrator.services import campaign_service as cs

    appended = []

    class Store:
        async def load_events(self, job_id):
            return [
                {"type": "RUN_COMPLETE", "seq": 0, "timestamp": 1},
                {"type": "STRATEGY_APPROVED", "seq": 1, "timestamp": 2},  # long quiet, not terminal
            ]

        async def append_event(self, job_id, event):
            appended.append(event)

    monkeypatch.setattr(cs, "get_storage", lambda: Store())

    async def frames():
        return [f async for f in cs.CampaignService().stream_job_events("j1")]

    out = asyncio.run(frames())
    assert len(out) == 2 and appended == []
    assert not any("RUN_FAILED" in f for f in out)
