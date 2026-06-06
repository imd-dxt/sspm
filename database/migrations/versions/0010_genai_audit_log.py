"""Add genai_audit_logs table for cloud LLM call telemetry

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-06 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "genai_audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("task",     sa.String(64), nullable=False),
        sa.Column("model",    sa.String(64), nullable=True),
        sa.Column("prompt_chars",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("response_chars", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pii_emails", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pii_uuids",  sa.Integer, nullable=False, server_default="0"),
        sa.Column("pii_ips",    sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_substituted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked",       sa.Boolean,    nullable=False, server_default=sa.false()),
        sa.Column("block_reason",  sa.String(256), nullable=True),
        sa.Column("latency_ms",    sa.Integer, nullable=True),
        sa.Column("actor",         sa.String(128), nullable=True),
    )
    op.create_index("ix_genai_audit_logs_timestamp", "genai_audit_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_genai_audit_logs_timestamp", "genai_audit_logs")
    op.drop_table("genai_audit_logs")
