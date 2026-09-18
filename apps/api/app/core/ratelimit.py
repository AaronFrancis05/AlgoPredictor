"""Sliding-window rate limiting on Redis sorted sets.

Usage:  @router.post(..., dependencies=[Depends(rate_limit("auth", settings.rate_limit_auth))])
The key is the authenticated user id when present, otherwise the client IP.
"""
import hmac
import ipaddress
import secrets
import time

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)


def parse_spec(spec: str) -> tuple[int, int]:
    count, _, seconds = spec.partition("/")
    return int(count), int(seconds)


def _valid_ip(value: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """The visitor's IP. Order of trust:
    1. X-Client-IP set by our own Next.js server, accepted only with the shared proxy secret
       (Next passes a client-sent X-Forwarded-For through unchanged, so that header cannot be trusted);
    2. X-Forwarded-For, counting `trusted_proxy_count` hops from the right (API behind a load balancer);
    3. the TCP peer (run uvicorn with --no-proxy-headers so this is never rewritten from headers)."""
    s = get_settings()
    secret = s.proxy_shared_secret.get_secret_value()
    if secret and hmac.compare_digest(request.headers.get("x-proxy-secret", ""), secret):
        ip = _valid_ip(request.headers.get("x-client-ip"))
        if ip:
            return ip
    xff = request.headers.get("x-forwarded-for")
    if s.trusted_proxy_count > 0 and xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= s.trusted_proxy_count:
            ip = _valid_ip(parts[-s.trusted_proxy_count])
            if ip:
                return ip
    return request.client.host if request.client else "unknown"


def ip_bucket(ip: str) -> str:
    """Rate-limit identity for an IP: IPv6 clients usually control a whole /64, so limit per /64."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


async def hit(key: str, limit: int, window: int) -> tuple[bool, int]:
    """Record one hit; return (allowed, retry_after_seconds)."""
    redis = get_redis()
    now = time.time()
    member = f"{now}:{secrets.token_hex(4)}"
    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.zrange(key, 0, 0, withscores=True)
        pipe.expire(key, window)
        _, _, count, oldest, _ = await pipe.execute()
    if count <= limit:
        return True, 0
    await redis.zrem(key, member)  # rejected hits do not extend the window
    retry = int(window - (now - oldest[0][1])) + 1 if oldest else window
    return False, max(retry, 1)


def rate_limit(scope: str, spec: str, fail_closed: bool = False):
    """fail_closed=True (auth endpoints) refuses requests when Redis is down instead of letting them through."""
    limit, window = parse_spec(spec)

    async def dependency(request: Request) -> None:
        who = getattr(request.state, "user_id", None) or ip_bucket(client_ip(request))
        try:
            allowed, retry = await hit(f"rl:{scope}:{who}", limit, window)
        except Exception as e:
            log.error("rate_limit_unavailable", scope=scope, error=str(e))
            if fail_closed:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Temporarily unavailable",
                                    headers={"Retry-After": "30"}) from e
            return
        if not allowed:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests",
                                headers={"Retry-After": str(retry)})

    return dependency
