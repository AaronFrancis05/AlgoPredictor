"""Change notifications pushed to open pages (Server-Sent Events).

An event only says WHAT changed ("live": scores or phases, "picks": newly published picks or results), never the
data: the page then refetches through the normal endpoints, which apply the viewer's plan. So the stream needs no
authentication and cannot leak a locked pick.

Fan-out: whoever changes data PUBLISHes one message on a Redis channel (one billed command). Each API process
holds at most one subscription, and only while at least one browser is connected, and hands every message to its
local connections through in-memory queues.
"""
import asyncio
import contextlib

from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)

CHANNEL = "ap:events"
KINDS = ("live", "picks")
QUEUE_SIZE = 16


async def publish(kind: str) -> None:
    """Tell open pages that `kind` changed. Never raises: a missed push only means the page's own schedule
    refetches a little later."""
    if kind not in KINDS:
        raise ValueError(kind)
    try:
        await get_redis().publish(CHANNEL, kind)
    except Exception as e:
        log.warning("event_publish_failed", kind=kind, error=str(e))


class Broker:
    """One Redis subscription per process, shared by every open stream in it."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[str]] = set()
        self._task: asyncio.Task | None = None

    @property
    def connections(self) -> int:
        return len(self._queues)

    def open(self) -> "asyncio.Queue[str]":
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._queues.add(q)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return q

    def close(self, q: "asyncio.Queue[str]") -> None:
        self._queues.discard(q)
        if not self._queues and self._task is not None:
            self._task.cancel()  # nobody listening: drop the subscription (and its health-check pings)
            self._task = None

    def deliver(self, kind: str) -> None:
        for q in list(self._queues):
            with contextlib.suppress(asyncio.QueueFull):  # a stalled client just misses a nudge
                q.put_nowait(kind)

    async def _run(self) -> None:
        delay = 1.0
        while self._queues:
            pubsub = get_redis().pubsub(ignore_subscribe_messages=True)
            try:
                await pubsub.subscribe(CHANNEL)
                delay = 1.0
                while self._queues:
                    msg = await pubsub.get_message(timeout=1.0)
                    if msg and msg.get("type") == "message" and msg.get("data") in KINDS:
                        self.deliver(msg["data"])
            except asyncio.CancelledError:
                raise
            except Exception as e:  # dropped connection: resubscribe with backoff
                log.warning("event_subscription_failed", error=str(e))
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()


broker = Broker()
