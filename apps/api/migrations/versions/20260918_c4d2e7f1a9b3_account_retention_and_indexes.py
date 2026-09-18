"""account retention columns and query indexes

- users.deleted_at / users.purge_after: closing an account disables it and schedules erasure
  (ACCOUNT_RETENTION_DAYS later) instead of deleting the row at once.
- Indexes for the hot queries: plan lookup, daily slip quota, data export, day's picks in kick-off order,
  user erasure (payments.user_id, ON DELETE SET NULL) and the worker's pending-webhook poll.

Revision ID: c4d2e7f1a9b3
Revises: b1f3a9c2d4e5
Create Date: 2026-09-18 21:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d2e7f1a9b3"
down_revision: str | None = "b1f3a9c2d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_purge_after", "users", ["purge_after"],
                    postgresql_where=sa.text("purge_after IS NOT NULL"))
    op.create_index("ix_subscriptions_user_status", "subscriptions", ["user_id", "status"])
    op.create_index("ix_slips_user_kind_created", "slips", ["user_id", "kind", "created_at"])
    op.create_index("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"])
    op.create_index("ix_picks_day_kickoff", "picks", ["kickoff_date", "kickoff_at"])
    op.create_index(op.f("ix_payments_user_id"), "payments", ["user_id"])
    op.create_index("ix_webhook_events_pending", "webhook_events", ["received_at"],
                    postgresql_where=sa.text("processed_at IS NULL"))


def downgrade() -> None:
    op.drop_index("ix_webhook_events_pending", table_name="webhook_events")
    op.drop_index(op.f("ix_payments_user_id"), table_name="payments")
    op.drop_index("ix_picks_day_kickoff", table_name="picks")
    op.drop_index("ix_audit_logs_user_created", table_name="audit_logs")
    op.drop_index("ix_slips_user_kind_created", table_name="slips")
    op.drop_index("ix_subscriptions_user_status", table_name="subscriptions")
    op.drop_index("ix_users_purge_after", table_name="users")
    op.drop_column("users", "purge_after")
    op.drop_column("users", "deleted_at")
