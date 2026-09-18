"""Alembic environment: async engine from app settings (works for local Postgres and Supabase)."""
import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.session import Base, engine_kwargs
import app.models  # noqa: F401  (register all tables)

target_metadata = Base.metadata
settings = get_settings()


def run_migrations_offline() -> None:
    """Emit SQL (alembic upgrade head --sql) without connecting."""
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.database_url,
                                 **engine_kwargs(settings.database_url, settings.db_ssl, settings.db_transaction_pooler))
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
