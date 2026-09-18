"""Server-Sent Events: publish -> Redis channel -> every open stream in the process."""
import asyncio

from app.core import events
from app.routers.events import stream


class FakeRequest:
    def __init__(self) -> None:
        self.gone = False

    async def is_disconnected(self) -> bool:
        return self.gone


async def _next_event(gen) -> str:
    """Next non-comment chunk from the stream (fails after 5 s)."""
    async with asyncio.timeout(5):
        while True:
            chunk = await gen.__anext__()
            if chunk.startswith("event:"):
                return chunk


async def test_published_change_reaches_open_streams_and_subscription_stops_when_idle():
    req = FakeRequest()
    gen = stream(req, heartbeat=0.2, max_seconds=10)
    first = await gen.__anext__()
    assert first.startswith("retry: ") and events.broker.connections == 1
    await asyncio.sleep(0.3)  # let the subscription start
    await events.publish("live")
    assert await _next_event(gen) == "event: live\ndata: {}\n\n"
    await events.publish("picks")
    assert await _next_event(gen) == "event: picks\ndata: {}\n\n"
    await gen.aclose()
    assert events.broker.connections == 0 and events.broker._task is None


async def test_stream_ends_on_disconnect_and_after_its_time_limit():
    req = FakeRequest()
    gen = stream(req, heartbeat=0.05, max_seconds=10)
    await gen.__anext__()
    req.gone = True
    chunks = [c async for c in gen]  # next heartbeat notices the disconnect and ends the stream
    assert all(c.startswith(":") for c in chunks) and events.broker.connections == 0
    gen = stream(FakeRequest(), heartbeat=0.05, max_seconds=0.2)
    assert [c async for c in gen][0].startswith("retry: ")
    assert events.broker.connections == 0


async def test_unknown_event_kinds_are_rejected():
    try:
        await events.publish("secrets")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
