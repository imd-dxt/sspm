"""Add condition_json to rules, ollama/impact fields to findings, activity_logs table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-10 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── rules: add condition_json, make detection_query nullable ─────────────
    op.add_column(
        "rules",
        sa.Column("condition_json", postgresql.JSONB, nullable=True),
    )
    # detection_query was NOT NULL — relax it for normalized rules
    op.alter_column("rules", "detection_query", nullable=True)

    # ── findings: add ollama_remediation + impact_factor ─────────────────────
    op.add_column(
        "findings",
        sa.Column("ollama_remediation", sa.Text, nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("impact_factor", sa.Float, nullable=True, server_default="0.5"),
    )

    # ── activity_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "connector_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("connectors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(320)),
        sa.Column("action", sa.String(256), nullable=False),
        sa.Column("resource", sa.String(512)),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw_json", postgresql.JSONB, server_default="{}"),
    )
    op.create_index("ix_activity_logs_connector_id", "activity_logs", ["connector_id"])
    op.create_index("ix_activity_logs_platform_ts", "activity_logs", ["platform", "timestamp"])
    op.create_index("ix_activity_logs_actor", "activity_logs", ["actor"])


def downgrade() -> None:
    op.drop_table("activity_logs")
    op.drop_column("findings", "impact_factor")
    op.drop_column("findings", "ollama_remediation")
    op.alter_column("rules", "detection_query", nullable=False)
    op.drop_column("rules", "condition_json")
