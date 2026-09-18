"""Shared async Redis client (overridden with fakeredis in tests).

Works with local Redis and with Upstash over TLS (rediss://). Upstash closes idle connections, so the pool
pings a connection that has been idle for more than 30 s before reusing it, keeps sockets alive, and retries
connection errors/timeouts with backoff instead of failing the request on the first dropped socket.
"""
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff

from app.core.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        s = get_settings()
        _client = Redis.from_url(
            s.redis_url,
            decode_responses=True,
            socket_connect_timeout=s.redis_timeout_seconds,
            socket_timeout=s.redis_timeout_seconds,
            socket_keepalive=True,
            health_check_interval=30,
            retry=Retry(ExponentialBackoff(cap=1.0, base=0.05), retries=3),
            retry_on_timeout=True,
        )
    return _client


def set_redis(client: Redis | None) -> None:
    global _client
    _client = client
