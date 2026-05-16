"""Add compliance_snapshots and compliance_reports tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-16 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compliance_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("framework", sa.String(64), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("total_rules", sa.Integer, nullable=False, server_default="0"),
        sa.Column("passed_rules", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_rules", sa.Integer, nullable=False, server_default="0"),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_compliance_snapshots_platform", "compliance_snapshots", ["platform"])
    op.create_index("ix_compliance_snapshots_framework", "compliance_snapshots", ["framework"])
    op.create_index("ix_compliance_snapshots_date", "compliance_snapshots", ["snapshot_date"])

    op.create_table(
        "compliance_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("framework", sa.String(64), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("total_rules", sa.Integer, nullable=False, server_default="0"),
        sa.Column("passed_rules", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_rules", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ai_narrative", sa.Text, nullable=True),
        sa.Column("pdf_path", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("compliance_reports")
    op.drop_index("ix_compliance_snapshots_date", table_name="compliance_snapshots")
    op.drop_index("ix_compliance_snapshots_framework", table_name="compliance_snapshots")
    op.drop_index("ix_compliance_snapshots_platform", table_name="compliance_snapshots")
    op.drop_table("compliance_snapshots")
