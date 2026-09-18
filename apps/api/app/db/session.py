"""Async SQLAlchemy engine/session. Works with local Postgres and Supabase.

Supabase notes:
- Direct / session pooler (port 5432): normal pooling.
- Transaction pooler (Supavisor, port 6543): prepared statements are not supported, so asyncpg's
  statement cache is disabled and SQLAlchemy uses NullPool (the pooler does the pooling).
- TLS is required (`db_ssl=require`).
"""
import ssl
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def engine_kwargs(url: str, db_ssl: str, transaction_pooler: bool, pool_size: int = 5, max_overflow: int = 5) -> dict:
    if url.startswith("sqlite"):
        return {}
    connect_args: dict = {}
    if db_ssl in ("require", "verify-full"):
        ctx = ssl.create_default_context()
        if db_ssl == "require":  # encrypted, hostname not pinned (Supabase pooler certificates)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
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
            s.database_url, s.db_ssl, s.db_transaction_pooler, s.db_pool_size, s.db_max_overflow))
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
