"""GET /api/v1/events: Server-Sent Events telling open pages when live scores or published picks changed."""
import asyncio
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.events import broker

router = APIRouter(tags=["events"])

MAX_CONNECTIONS = 1000        # per API process; beyond this clients fall back to their refetch schedule
HEARTBEAT_SECONDS = 25        # comment lines keep proxies from closing an idle stream
MAX_STREAM_SECONDS = 600      # end the response now and then; EventSource reconnects by itself
RETRY_MS = 5000


async def stream(request: Request, *, heartbeat: float = HEARTBEAT_SECONDS,
                 max_seconds: float = MAX_STREAM_SECONDS) -> AsyncIterator[str]:
    queue = broker.open()  # opened here, so the finally below always releases it
    try:
        yield f"retry: {RETRY_MS}\n: connected\n\n"
        end = time.monotonic() + max_seconds
        while (left := end - time.monotonic()) > 0:
            try:
                kind = await asyncio.wait_for(queue.get(), timeout=min(heartbeat, left))
                yield f"event: {kind}\ndata: {{}}\n\n"
            except TimeoutError:
                if await request.is_disconnected():
                    return
                yield ": ping\n\n"
    finally:
        broker.close(queue)


@router.get("/events", include_in_schema=False)
async def events(request: Request) -> StreamingResponse:
    """Named events `live` and `picks` with an empty payload: refetch that data when one arrives."""
    if broker.connections >= MAX_CONNECTIONS:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Too many open streams",
                            headers={"Retry-After": "60"})
    return StreamingResponse(stream(request), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
