"""Two-level cache-aside: a small in-process layer (L1) in front of Redis (L2).

Redis keys are versioned by a 'generation' counter per namespace, so one INCR invalidates every cached entry of
that namespace (used after each ingest). L1 keeps hot entries for a few seconds so a busy endpoint does not pay
two Redis round trips per request; other API instances can therefore serve an entry up to L1_TTL_SECONDS after
it was invalidated. A cache failure never breaks the request: it falls through to the producer.
"""
import json
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)

L1_TTL_SECONDS = 10.0
L1_MAX_ENTRIES = 512
_l1: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()


def _l1_get(key: str) -> tuple[bool, Any]:
    hit = _l1.get(key)
    if hit is None:
        return False, None
    expires, value = hit
    if expires < time.monotonic():
        _l1.pop(key, None)
        return False, None
    _l1.move_to_end(key)
    return True, value


def _l1_set(key: str, value: Any, ttl: float) -> None:
    _l1[key] = (time.monotonic() + min(ttl, L1_TTL_SECONDS), value)
    _l1.move_to_end(key)
    while len(_l1) > L1_MAX_ENTRIES:
        _l1.popitem(last=False)


def _l1_drop(prefix: str) -> None:
    for k in [k for k in _l1 if k.startswith(prefix)]:
        _l1.pop(k, None)


def clear_local() -> None:
    _l1.clear()
    _gen_l1.clear()


_gen_l1: dict[str, tuple[float, str]] = {}


async def _generation(namespace: str) -> str:
    """The namespace's generation, remembered locally for L1_TTL_SECONDS: an L1 miss then costs one Redis GET
    instead of two. Another instance's invalidate() reaches this one within the same bound as L1 itself."""
    hit = _gen_l1.get(namespace)
    if hit is not None and hit[0] >= time.monotonic():
        return hit[1]
    gen = await get_redis().get(f"cachegen:{namespace}") or "0"
    _gen_l1[namespace] = (time.monotonic() + L1_TTL_SECONDS, gen)
    return gen


async def cached(namespace: str, key: str, ttl: int, producer: Callable[[], Awaitable[Any]]) -> Any:
    local_key = f"{namespace}:{key}"
    found, value = _l1_get(local_key)
    if found:
        return value
    redis = get_redis()
    full = None
    try:
        full = f"cache:{namespace}:{await _generation(namespace)}:{key}"
        hit = await redis.get(full)
        if hit is not None:
            value = json.loads(hit)
            _l1_set(local_key, value, ttl)
            return value
    except Exception as e:  # cache failures must never break the request
        log.warning("cache_get_failed", error=str(e))
    value = await producer()
    # round-trip through JSON so L1 and Redis hand callers the same shapes (dates as strings)
    value = json.loads(json.dumps(value, default=str))
    _l1_set(local_key, value, ttl)
    if full is not None:
        try:
            await redis.set(full, json.dumps(value), ex=ttl)
        except Exception as e:
            log.warning("cache_set_failed", error=str(e))
    return value


async def forget(namespace: str, key: str) -> None:
    """Drop one entry (e.g. a user's plan after a payment)."""
    _l1.pop(f"{namespace}:{key}", None)
    try:
        await get_redis().delete(f"cache:{namespace}:{await _generation(namespace)}:{key}")
    except Exception as e:
        log.warning("cache_forget_failed", error=str(e))


async def invalidate(namespace: str) -> None:
    try:
        await get_redis().incr(f"cachegen:{namespace}")
    finally:  # drop local copies after the bump, so a concurrent request cannot re-cache the old generation
        _l1_drop(f"{namespace}:")
        _gen_l1.pop(namespace, None)
