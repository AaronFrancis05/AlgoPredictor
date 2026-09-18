"""FastAPI application factory."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    CSRFMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.ratelimit import rate_limit
from app.db.session import dispose_engine
from app.routers import admin, auth, billing, health, internal, picks, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level)
    docs = not s.is_production
    app = FastAPI(title=f"{s.app_name} API", version="0.1.0", lifespan=lifespan,
                  docs_url="/docs" if docs else None, redoc_url=None,
                  openapi_url="/openapi.json" if docs else None,
                  description="Model-based football predictions. Probabilities, not guarantees. 18+.")

    # middleware runs bottom-up: the last added is the outermost
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=2_000_000)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["content-type", "x-csrf-token", "authorization", "x-api-key", "x-request-id"],
                       max_age=600)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=s.trusted_hosts)
    app.add_middleware(SecurityHeadersMiddleware, hsts=s.is_production)
    app.add_middleware(RequestContextMiddleware)
    # pick lists are repetitive JSON: gzip cuts them several-fold for mobile connections
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    default_limit = rate_limit("default", s.rate_limit_default)
    from fastapi import Depends
    api_deps = [Depends(default_limit)]
    for r in (auth.router, users.router, picks.router, billing.router, admin.router):
        app.include_router(r, prefix=s.api_prefix, dependencies=api_deps)
    app.include_router(billing.webhooks)
    app.include_router(internal.router)
    app.include_router(health.router)
    Instrumentator(excluded_handlers=["/healthz", "/readyz", "/metrics"]).instrument(app).expose(
        app, include_in_schema=False)
    return app


app = create_app()
