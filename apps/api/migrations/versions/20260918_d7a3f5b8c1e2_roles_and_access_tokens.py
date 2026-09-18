"""user roles and admin-issued access tokens

- users.role ("user" | "admin") replaces users.is_admin (existing admins are carried over). is_admin is kept,
  unused, so the API deployed before this migration keeps working; a later migration drops it.
- access_tokens: codes (stored as SHA-256 digests) that grant a paid plan until they expire.
- subscriptions.access_token_id links a redemption to its token; one redemption per user per token.
- access_tokens gets the same Supabase lock-down as every other table (RLS on, Data API roles revoked).

Revision ID: d7a3f5b8c1e2
Revises: c4d2e7f1a9b3
Create Date: 2026-09-18 22:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7a3f5b8c1e2"
down_revision: str | None = "c4d2e7f1a9b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="user"))
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin")
    # Expand, then contract: is_admin stays until every running API reads role (the code deployed before this
    # migration still selects it). It gets a default so the new code, which no longer sets it, can insert users.
    # Drop it in a later migration once the new API is live everywhere.
    with op.batch_alter_table("users") as b:
        b.alter_column("is_admin", existing_type=sa.Boolean(), existing_nullable=False, server_default=sa.false())

    op.create_table(
        "access_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column("code_hint", sa.String(12), nullable=False),
        sa.Column("plan_code", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(120), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plan_code"], ["plans.code"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_digest"),
    )
    op.create_index(op.f("ix_access_tokens_expires_at"), "access_tokens", ["expires_at"])

    with op.batch_alter_table("subscriptions") as b:
        b.add_column(sa.Column("access_token_id", sa.Uuid(), nullable=True))
        b.create_foreign_key("fk_subscriptions_access_token_id", "access_tokens", ["access_token_id"], ["id"],
                             ondelete="SET NULL")
        b.create_unique_constraint("uq_subscriptions_access_token_id_user_id", ["access_token_id", "user_id"])
    op.create_index(op.f("ix_subscriptions_access_token_id"), "subscriptions", ["access_token_id"])

    if op.get_context().dialect.name == "postgresql":
        op.execute('ALTER TABLE public."access_tokens" ENABLE ROW LEVEL SECURITY')
        op.execute("""
            DO $$
            DECLARE r text;
            BEGIN
              FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                  EXECUTE format('REVOKE ALL ON public."access_tokens" FROM %I', r);
                END IF;
              END LOOP;
            END $$;
        """)


def downgrade() -> None:
    op.drop_index(op.f("ix_subscriptions_access_token_id"), table_name="subscriptions")
    with op.batch_alter_table("subscriptions") as b:
        b.drop_constraint("uq_subscriptions_access_token_id_user_id", type_="unique")
        b.drop_constraint("fk_subscriptions_access_token_id", type_="foreignkey")
        b.drop_column("access_token_id")
    op.drop_index(op.f("ix_access_tokens_expires_at"), table_name="access_tokens")
    op.drop_table("access_tokens")
    op.execute("UPDATE users SET is_admin = (role = 'admin')")
    with op.batch_alter_table("users") as b:
        b.alter_column("is_admin", existing_type=sa.Boolean(), existing_nullable=False, server_default=None)
        b.drop_column("role")
