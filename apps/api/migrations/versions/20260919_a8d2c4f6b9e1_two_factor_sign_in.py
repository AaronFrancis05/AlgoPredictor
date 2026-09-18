"""two-factor sign-in (TOTP) columns

Revision ID: a8d2c4f6b9e1
Revises: f2c8a6d4b7e3
Create Date: 2026-09-19 02:30:00

Adds nullable columns only (and one with a server default), so the running API keeps working while this is applied.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8d2c4f6b9e1"
down_revision: str | None = "f2c8a6d4b7e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_enc", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("mfa_recovery_digests", sa.JSON(), nullable=True))
    op.add_column("refresh_tokens", sa.Column("mfa", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("refresh_tokens", "mfa")
    op.drop_column("users", "mfa_recovery_digests")
    op.drop_column("users", "totp_last_step")
    op.drop_column("users", "totp_enabled_at")
    op.drop_column("users", "totp_secret_enc")
