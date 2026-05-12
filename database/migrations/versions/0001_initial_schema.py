"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── connectors ────────────────────────────────────────────────────────────
    op.create_table(
        "connectors",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("platform_name", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("credentials_encrypted", sa.Text, nullable=False),
        sa.Column("config_json", postgresql.JSONB, server_default="{}"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── scan_runs ─────────────────────────────────────────────────────────────
    op.create_table(
        "scan_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("connector_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("records_fetched", sa.Integer, server_default="0"),
        sa.Column("errors_json", postgresql.JSONB, server_default="[]"),
    )
    op.create_index("ix_scan_runs_connector_id", "scan_runs", ["connector_id"])

    # ── normalized_entities ───────────────────────────────────────────────────
    op.create_table(
        "normalized_entities",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("platform_id", sa.String(256), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("data_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_normalized_entities_email", "normalized_entities", ["email"])
    op.create_index(
        "ix_normalized_entities_platform_type_id",
        "normalized_entities",
        ["platform", "entity_type", "platform_id"],
        unique=True,
    )

    # ── findings ──────────────────────────────────────────────────────────────
    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("rule_id", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("affected_entity_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("normalized_entities.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("remediation", sa.Text, server_default=""),
        sa.Column("evidence_json", postgresql.JSONB, server_default="{}"),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_findings_rule_id", "findings", ["rule_id"])
    op.create_index("ix_findings_affected_entity_id", "findings", ["affected_entity_id"])
    op.create_index("ix_findings_severity_status", "findings", ["severity", "status"])


def downgrade() -> None:
    op.drop_table("findings")
    op.drop_table("normalized_entities")
    op.drop_table("scan_runs")
    op.drop_table("connectors")
