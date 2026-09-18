"""HTTP middleware: request id + access log, security headers, body-size limit, CSRF (double submit), ETags."""
import hashlib
import hmac
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger

log = get_logger("http")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PREFIXES = ("/webhooks/", "/internal/", "/api/v1/auth/login", "/api/v1/auth/register",
                        "/api/v1/auth/refresh", "/api/v1/auth/password", "/api/v1/auth/verify-email",
                        "/api/v1/auth/google", "/api/v1/auth/mfa")  # all pre-authentication


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        log.info("request", method=request.method, path=request.url.path, status=response.status_code,
                 ms=round((time.perf_counter() - start) * 1000, 1))
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, hsts: bool):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if not request.url.path.startswith(("/docs", "/redoc")):
            h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if self.hsts:
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int = 2_000_000):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > self.max_bytes:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)


class ETagMiddleware:
    """Weak ETag on successful JSON GET responses; `If-None-Match` with the same tag gets 304 without a body.
    Pages poll pick lists that change a few times a day, so most polls become a few hundred bytes. The browser
    sends If-None-Match by itself once its cached copy is older than Cache-Control max-age. Pure ASGI (it must
    buffer the body to hash it); add it inside GZip so the tag is computed on the uncompressed JSON."""

    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET" or not scope["path"].startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        wanted = next((v.decode() for k, v in scope["headers"] if k == b"if-none-match"), None)
        start: dict | None = None
        chunks: list[bytes] = []
        passthrough = False

        async def wrapped(message) -> None:
            nonlocal start, passthrough
            if passthrough:
                await send(message)
                return
            if message["type"] == "http.response.start":
                ctype = next((v for k, v in message["headers"] if k == b"content-type"), b"")
                if message["status"] != 200 or not ctype.startswith(b"application/json"):
                    passthrough = True
                    await send(message)
                    return
                start = message
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return
            body = b"".join(chunks)
            tag = f'W/"{hashlib.sha256(body).hexdigest()[:32]}"'
            headers = [(k, v) for k, v in start["headers"] if k != b"content-length"]
            headers.append((b"etag", tag.encode()))
            candidates = {t.strip() for t in wanted.split(",")} if wanted else set()
            if "*" in candidates or tag in candidates:
                await send({"type": "http.response.start", "status": 304, "headers": [
                    (k, v) for k, v in headers if k in (b"etag", b"cache-control", b"vary", b"x-request-id")]})
                await send({"type": "http.response.body", "body": b""})
                return
            headers.append((b"content-length", str(len(body)).encode()))
            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, wrapped)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Cookie-authenticated unsafe requests must echo the ap_csrf cookie in the X-CSRF-Token header.
    Requests authenticated by bearer token or API key are not CSRF-able and are skipped."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in SAFE_METHODS or request.url.path.startswith(CSRF_EXEMPT_PREFIXES):
            return await call_next(request)
        if request.headers.get("authorization") or request.headers.get("x-api-key"):
            return await call_next(request)
        if "ap_access" not in request.cookies and "ap_refresh" not in request.cookies:
            return await call_next(request)
        cookie = request.cookies.get("ap_csrf", "")
        header = request.headers.get("x-csrf-token", "")
        if not cookie or not hmac.compare_digest(cookie, header):
            return JSONResponse({"detail": "CSRF token missing or invalid"}, status_code=403)
        return await call_next(request)
