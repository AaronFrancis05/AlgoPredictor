"""live match state (live-score feed) and confirmed team-name aliases

Revision ID: e5b9c3d7f2a1
Revises: d7a3f5b8c1e2
Create Date: 2026-09-18 23:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b9c3d7f2a1"
down_revision: str | None = "d7a3f5b8c1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("live_matches", "live_team_aliases")


def upgrade() -> None:
    op.create_table(
        "live_matches",
        sa.Column("match_key", sa.String(200), nullable=False),
        sa.Column("kickoff_date", sa.Date(), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("league_code", sa.String(8), nullable=False),
        sa.Column("home_team", sa.String(80), nullable=False),
        sa.Column("away_team", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("link_method", sa.String(16), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("elapsed", sa.Integer(), nullable=True),
        sa.Column("home_goals", sa.Integer(), nullable=True),
        sa.Column("away_goals", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("match_key"),
    )
    op.create_index(op.f("ix_live_matches_kickoff_date"), "live_matches", ["kickoff_date"])
    op.create_index(op.f("ix_live_matches_kickoff_at"), "live_matches", ["kickoff_at"])
    op.create_index(op.f("ix_live_matches_fixture_id"), "live_matches", ["fixture_id"])
    op.create_table(
        "live_team_aliases",
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_name", sa.String(120), nullable=False),
        sa.Column("team", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider", "provider_name"),
    )
    if op.get_context().dialect.name == "postgresql":
        for t in TABLES:  # same Supabase lock-down as every other table
            op.execute(f'ALTER TABLE public."{t}" ENABLE ROW LEVEL SECURITY')
            op.execute(f"""
                DO $$
                DECLARE r text;
                BEGIN
                  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                      EXECUTE format('REVOKE ALL ON public."{t}" FROM %I', r);
                    END IF;
                  END LOOP;
                END $$;
            """)  # noqa: S608 - constant table names


def downgrade() -> None:
    op.drop_table("live_team_aliases")
    op.drop_index(op.f("ix_live_matches_fixture_id"), table_name="live_matches")
    op.drop_index(op.f("ix_live_matches_kickoff_at"), table_name="live_matches")
    op.drop_index(op.f("ix_live_matches_kickoff_date"), table_name="live_matches")
    op.drop_table("live_matches")
