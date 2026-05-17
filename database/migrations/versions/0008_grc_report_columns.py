"""Add GRC report columns to compliance_reports and scan_run_id to compliance_snapshots

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-17 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # compliance_snapshots: add scan_run_id
    op.add_column(
        "compliance_snapshots",
        sa.Column("scan_run_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_compliance_snapshots_scan_run_id",
        "compliance_snapshots",
        ["scan_run_id"],
    )

    # compliance_reports: add GRC report fields
    op.add_column(
        "compliance_reports",
        sa.Column("status", sa.String(32), nullable=False, server_default="complete"),
    )
    op.add_column(
        "compliance_reports",
        sa.Column("findings_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "compliance_reports",
        sa.Column("report_title", sa.String(256), nullable=True),
    )
    op.add_column(
        "compliance_reports",
        sa.Column("platforms_assessed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "compliance_reports",
        sa.Column("frameworks_assessed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("compliance_reports", "frameworks_assessed")
    op.drop_column("compliance_reports", "platforms_assessed")
    op.drop_column("compliance_reports", "report_title")
    op.drop_column("compliance_reports", "findings_snapshot")
    op.drop_column("compliance_reports", "status")

    op.drop_index("ix_compliance_snapshots_scan_run_id", table_name="compliance_snapshots")
    op.drop_column("compliance_snapshots", "scan_run_id")
