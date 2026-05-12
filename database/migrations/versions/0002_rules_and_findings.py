"""rules and findings schema update

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Add findings_count to scan_runs ───────────────────────────────────────
    op.add_column("scan_runs", sa.Column("findings_count", sa.Integer, server_default="0"))

    # ── Drop old findings table (Phase 1 schema – no FK safety needed) ────────
    op.execute("DROP TABLE IF EXISTS findings CASCADE")

    # ── Create rules table ────────────────────────────────────────────────────
    op.create_table(
        "rules",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("cis_control", sa.String(32)),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("profile", sa.String(32)),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("rationale", sa.Text, server_default=""),
        sa.Column("detection_query", sa.Text, nullable=False),
        sa.Column("query_type", sa.String(16), server_default="cypher"),
        sa.Column("resource_id_field", sa.String(64), server_default="repository"),
        sa.Column("remediation", sa.Text, server_default=""),
        sa.Column("compliance_mapping", postgresql.JSONB, server_default="[]"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_rules_platform", "rules", ["platform"])
    op.create_index("ix_rules_severity", "rules", ["severity"])

    # ── Create new findings table ─────────────────────────────────────────────
    op.create_table(
        "findings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rule_id", sa.String(64), sa.ForeignKey("rules.id"), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_identifier", sa.String(512), nullable=False),
        sa.Column("resource_name", sa.String(512)),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("evidence", postgresql.JSONB, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("first_detected", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_detected", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("scan_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("scan_runs.id")),
    )
    op.create_index("ix_findings_rule_id", "findings", ["rule_id"])
    op.create_index("ix_findings_status_severity", "findings", ["status", "severity"])
    op.create_index("ix_findings_resource", "findings", ["platform", "resource_identifier"])
    op.create_index("ix_findings_scan_run", "findings", ["scan_run_id"])
    # Unique constraint for deduplication
    op.create_index(
        "ix_findings_dedup",
        "findings",
        ["rule_id", "resource_identifier", "status"],
    )


def downgrade() -> None:
    op.drop_table("findings")
    op.drop_table("rules")
    op.drop_column("scan_runs", "findings_count")
