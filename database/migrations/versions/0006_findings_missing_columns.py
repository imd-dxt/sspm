"""Add missing columns to findings and connectors tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-12 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── findings: status workflow columns ────────────────────────────────────
    op.add_column("findings", sa.Column("justification", sa.Text, nullable=True))
    op.add_column("findings", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))

    # ── connectors: health + schedule columns ────────────────────────────────
    op.add_column("connectors", sa.Column("connection_ok", sa.Boolean, nullable=True))
    op.add_column("connectors", sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("connectors", sa.Column("last_sync_error", sa.Text, nullable=True))
    op.add_column("connectors", sa.Column("sync_interval_minutes", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("connectors", "sync_interval_minutes")
    op.drop_column("connectors", "last_sync_error")
    op.drop_column("connectors", "last_sync_at")
    op.drop_column("connectors", "connection_ok")
    op.drop_column("findings", "status_changed_at")
    op.drop_column("findings", "justification")
