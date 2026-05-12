"""Add referentials to rules; add ollama/impact fields to findings

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-10 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── rules: referentials array ─────────────────────────────────────────────
    op.add_column(
        "rules",
        sa.Column("referentials", postgresql.JSONB, nullable=True, server_default="[]"),
    )

    # ── findings: Ollama-generated remediation + impact explanation ───────────
    op.add_column("findings", sa.Column("generated_remediation", sa.Text, nullable=True))
    op.add_column(
        "findings",
        sa.Column("remediation_source", sa.String(16), nullable=True),  # "static" | "ollama"
    )
    op.add_column("findings", sa.Column("impact_explanation", sa.Text, nullable=True))
    op.add_column(
        "findings",
        sa.Column("impact_source", sa.String(16), nullable=True),  # "ollama" | "static"
    )


def downgrade() -> None:
    op.drop_column("findings", "impact_source")
    op.drop_column("findings", "impact_explanation")
    op.drop_column("findings", "remediation_source")
    op.drop_column("findings", "generated_remediation")
    op.drop_column("rules", "referentials")
