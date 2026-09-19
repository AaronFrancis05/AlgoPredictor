"""user notifications (in-app inbox)

Revision ID: c9e4a2f7d1b6
Revises: b3e7d1a5c9f2
Create Date: 2026-09-19 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e4a2f7d1b6"
down_revision: str | None = "b3e7d1a5c9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("link", sa.String(200), nullable=True),
        sa.Column("dedupe_key", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dedupe_key"),
    )
    op.create_index("ix_user_notifications_user_created", "user_notifications", ["user_id", "created_at"])
    if op.get_context().dialect.name == "postgresql":  # same Supabase lock-down as every other table
        op.execute('ALTER TABLE public."user_notifications" ENABLE ROW LEVEL SECURITY')
        op.execute("""
            DO $$
            DECLARE r text;
            BEGIN
              FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                  EXECUTE format('REVOKE ALL ON public."user_notifications" FROM %I', r);
                END IF;
              END LOOP;
            END $$;
        """)


def downgrade() -> None:
    op.drop_index("ix_user_notifications_user_created", table_name="user_notifications")
    op.drop_table("user_notifications")
