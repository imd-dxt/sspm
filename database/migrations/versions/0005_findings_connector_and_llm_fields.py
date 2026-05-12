"""Add connector attribution and LLM analysis fields to findings

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-12 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── findings: connector attribution ──────────────────────────────────────
    op.add_column(
        "findings",
        sa.Column(
            "connector_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("connectors.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    op.add_column("findings", sa.Column("connector_name", sa.String(256), nullable=True))

    # ── findings: LLM analysis fields ────────────────────────────────────────
    op.add_column("findings", sa.Column("llm_severity", sa.String(16), nullable=True))
    op.add_column("findings", sa.Column("llm_severity_reasoning", sa.Text, nullable=True))
    op.add_column("findings", sa.Column("llm_exploitability", sa.Text, nullable=True))
    op.add_column("findings", sa.Column("llm_remediation", sa.Text, nullable=True))
    op.add_column("findings", sa.Column("llm_confidence", sa.Float, nullable=True))
    op.add_column("findings", sa.Column("llm_analyzed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("findings", "llm_analyzed_at")
    op.drop_column("findings", "llm_confidence")
    op.drop_column("findings", "llm_remediation")
    op.drop_column("findings", "llm_exploitability")
    op.drop_column("findings", "llm_severity_reasoning")
    op.drop_column("findings", "llm_severity")
    op.drop_column("findings", "connector_name")
    op.drop_index("ix_findings_connector_id", table_name="findings")
    op.drop_column("findings", "connector_id")
