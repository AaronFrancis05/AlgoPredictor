"""Two-level cache: invalidation must hold even after Redis loses its keys (eviction, restart, FLUSHALL)."""
from app.core import cache
from app.core.redis import get_redis


async def test_invalidate_after_redis_lost_its_keys_does_not_revive_a_stale_entry():
    ns = "t_flush"
    cache.clear_local()
    await cache.invalidate(ns)  # the namespace has been invalidated before: generation is no longer the default
    value = {"v": "old"}

    async def produce():
        return value

    assert await cache.cached(ns, "u", 60, produce) == {"v": "old"}
    await get_redis().flushall()  # Redis loses everything; this process still remembers the generation
    cache._l1.clear()  # its L1 copy expires (or another instance serves the next read)
    assert await cache.cached(ns, "u", 60, produce) == {"v": "old"}  # re-cached before the data changes

    value = {"v": "new"}  # the data changes, then the namespace is invalidated as usual
    await cache.invalidate(ns)
    assert await cache.cached(ns, "u", 60, produce) == {"v": "new"}
