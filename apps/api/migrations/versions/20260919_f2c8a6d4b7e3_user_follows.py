"""user follows (matches and leagues)

Revision ID: f2c8a6d4b7e3
Revises: e5b9c3d7f2a1
Create Date: 2026-09-19 01:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c8a6d4b7e3"
down_revision: str | None = "e5b9c3d7f2a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_follows",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "kind", "target"),
    )
    if op.get_context().dialect.name == "postgresql":  # same Supabase lock-down as every other table
        op.execute('ALTER TABLE public."user_follows" ENABLE ROW LEVEL SECURITY')
        op.execute("""
            DO $$
            DECLARE r text;
            BEGIN
              FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                  EXECUTE format('REVOKE ALL ON public."user_follows" FROM %I', r);
                END IF;
              END LOOP;
            END $$;
        """)


def downgrade() -> None:
    op.drop_table("user_follows")
