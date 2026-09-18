"""restricted database role for the API and worker

Revision ID: b3e7d1a5c9f2
Revises: a8d2c4f6b9e1
Create Date: 2026-09-19 03:00:00

The API used to connect as `postgres`, the owner of every table: a bug or SQL injection could then ALTER, DROP,
disable RLS, or reach Supabase's other schemas. `algopredict_app` can only read and write rows in public tables.

- NOLOGIN here, and no password in code. To use it, run once in the Supabase SQL editor (as postgres):
      ALTER ROLE algopredict_app WITH LOGIN PASSWORD '<a new random password>';
  then set DATABASE_URL on Railway (api + worker) to
      postgresql+asyncpg://algopredict_app.<project_ref>:<password>@<pooler host>:5432/postgres
  and keep the owner URL only in MIGRATION_DATABASE_URL, used by `alembic upgrade`.
- BYPASSRLS: RLS is on (with no policies) only to shut the Supabase Data API; the app must still see every row.
- Default privileges cover tables that later migrations (run as postgres) create.
Postgres only; a no-op on SQLite.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b3e7d1a5c9f2"
down_revision: str | None = "a8d2c4f6b9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "algopredict_app"


def upgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute(f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
            CREATE ROLE {ROLE} NOLOGIN NOINHERIT BYPASSRLS;
          END IF;
        END $$;
    """)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}")
    op.execute(f"REVOKE ALL ON public.alembic_version FROM {ROLE}")  # schema history is the owner's business
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {ROLE}")


def downgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {ROLE}")
