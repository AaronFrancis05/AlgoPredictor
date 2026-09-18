"""Async SQLAlchemy engine/session. Works with local Postgres and Supabase.

Supabase notes:
- Direct / session pooler (port 5432): normal pooling.
- Transaction pooler (Supavisor, port 6543): prepared statements are not supported, so asyncpg's
  statement cache is disabled and SQLAlchemy uses NullPool (the pooler does the pooling).
- TLS: use `db_ssl=verify-full`. It checks the server certificate against the Supabase root CA bundled in
  certs/ (the same file as prod-ca-2021.crt from the dashboard) and the hostname (*.pooler.supabase.com).
  `require` encrypts but accepts any certificate, so an attacker on the network path could impersonate the database.
"""
import ssl
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


API_ROOT = Path(__file__).resolve().parents[2]  # apps/api (/app in the image)
DEFAULT_CA = "certs/supabase-prod-ca-2021.crt"


def ssl_context(db_ssl: str, root_cert: str = "") -> ssl.SSLContext | None:
    """None for `disable`. `verify-full` trusts only `root_cert` (a path, relative to apps/api) and checks the hostname;
    `require` encrypts without verifying anything."""
    if db_ssl == "disable":
        return None
    if db_ssl == "verify-full":
        path = Path(root_cert or DEFAULT_CA)
        path = path if path.is_absolute() else API_ROOT / path
        if not path.is_file():
            raise RuntimeError(f"DB_SSL=verify-full but the CA file {path} does not exist")
        return ssl.create_default_context(cafile=str(path))  # CERT_REQUIRED + check_hostname
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def engine_kwargs(url: str, db_ssl: str, transaction_pooler: bool, pool_size: int = 5, max_overflow: int = 5,
                  root_cert: str = "") -> dict:
    if url.startswith("sqlite"):
        return {}
    connect_args: dict = {}
    ctx = ssl_context(db_ssl, root_cert)
    if ctx is not None:
        connect_args["ssl"] = ctx
    if transaction_pooler:
        connect_args.update(statement_cache_size=0, prepared_statement_cache_size=0)
        return dict(poolclass=NullPool, connect_args=connect_args)
    return dict(pool_size=pool_size, max_overflow=max_overflow, pool_pre_ping=True, pool_recycle=1800,
                connect_args=connect_args)


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        s = get_settings()
        _engine = create_async_engine(s.database_url, **engine_kwargs(
            s.database_url, s.db_ssl, s.db_transaction_pooler, s.db_pool_size, s.db_max_overflow, s.db_ssl_root_cert))
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine, _sessionmaker = None, None
