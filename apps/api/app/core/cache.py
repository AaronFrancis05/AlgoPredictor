"""Cache-aside helpers on Redis. Keys are versioned by a 'generation' counter per namespace, so one INCR
invalidates every cached entry of that namespace (used after each ingest)."""
import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)


async def _generation(namespace: str) -> str:
    return await get_redis().get(f"cachegen:{namespace}") or "0"


async def cached(namespace: str, key: str, ttl: int, producer: Callable[[], Awaitable[Any]]) -> Any:
    redis = get_redis()
    full = f"cache:{namespace}:{await _generation(namespace)}:{key}"
    try:
        hit = await redis.get(full)
        if hit is not None:
            return json.loads(hit)
    except Exception as e:  # cache failures must never break the request
        log.warning("cache_get_failed", error=str(e))
    value = await producer()
    try:
        await redis.set(full, json.dumps(value, default=str), ex=ttl)
    except Exception as e:
        log.warning("cache_set_failed", error=str(e))
    return value


async def invalidate(namespace: str) -> None:
    await get_redis().incr(f"cachegen:{namespace}")
