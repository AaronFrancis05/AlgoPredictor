"""lock down tables for Supabase: RLS on, no policies, revoke Data API roles

The API reaches Postgres directly as the table owner (which bypasses RLS). Supabase also exposes the
public schema through its Data API (PostgREST) to the `anon` and `authenticated` roles; enabling RLS
without any policy plus revoking their privileges means that path can read or change nothing.
Safe on plain Postgres (role checks) and skipped on SQLite.

Revision ID: b1f3a9c2d4e5
Revises: 9c255e0320d9
Create Date: 2026-09-18 07:40:00
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b1f3a9c2d4e5"
down_revision: str | None = "9c255e0320d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ["users", "oauth_accounts", "refresh_tokens", "email_tokens", "plans", "prices", "subscriptions",
          "payments", "webhook_events", "picks", "pick_results", "slips", "audit_logs", "alembic_version"]


def upgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return
    for t in TABLES:
        # ENABLE only (not FORCE): the owning role used by the API must keep bypassing RLS
        op.execute(f'ALTER TABLE public."{t}" ENABLE ROW LEVEL SECURITY')
    tables = ", ".join(f'public."{t}"' for t in TABLES)
    op.execute(f"""
        DO $$
        DECLARE r text;
        BEGIN
          FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
              EXECUTE format('REVOKE ALL ON {tables} FROM %I', r);
            END IF;
          END LOOP;
        END $$;
    """)


def downgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return
    for t in TABLES:
        op.execute(f'ALTER TABLE public."{t}" DISABLE ROW LEVEL SECURITY')
