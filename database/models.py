"""
SQLAlchemy ORM models.

Tables:
  connectors          – registered SaaS platform connectors
  scan_runs           – one row per sync execution
  normalized_entities – deduplicated SaaS entities
  rules               – detection rules loaded from YAML / DB
  findings            – detected security misconfigurations
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


_FK_CONNECTOR = "connectors.id"


# ── Connector ─────────────────────────────────────────────────────────────────

class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    platform_name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Connection health (populated after each sync)
    connection_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(Text)

    # Auto-sync schedule (NULL = disabled)
    sync_interval_minutes: Mapped[int | None] = mapped_column(Integer)

    scan_runs: Mapped[list["ScanRun"]] = relationship("ScanRun", back_populates="connector", cascade="all, delete-orphan")


# ── ScanRun ───────────────────────────────────────────────────────────────────

class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    connector_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey(_FK_CONNECTOR), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    errors_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    connector: Mapped["Connector"] = relationship("Connector", back_populates="scan_runs")

    @property
    def errors(self) -> list:
        return self.errors_json or []


# ── NormalizedEntity ──────────────────────────────────────────────────────────

class NormalizedEntity(Base):
    __tablename__ = "normalized_entities"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    platform_id: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Rule ──────────────────────────────────────────────────────────────────────

class Rule(Base):
    """Security detection rule. Loaded from YAML, stored in DB for runtime execution."""
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)          # e.g. "CIS-GH-1.1.3"
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)       # github | entra | jira
    cis_control: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), nullable=False)        # critical|high|medium|low
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    profile: Mapped[str | None] = mapped_column(String(32))                  # Level 1 | Level 2
    description: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    detection_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_type: Mapped[str] = mapped_column(String(16), default="cypher")    # cypher | sql | normalized
    resource_id_field: Mapped[str] = mapped_column(String(64), default="repository")  # which RETURN col = identifier
    condition_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # for query_type=normalized
    referentials: Mapped[list[str]] = mapped_column(JSONB, default=list)  # e.g. ["CIS", "ISO27001"]
    remediation: Mapped[str] = mapped_column(Text, default="")
    compliance_mapping: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    findings: Mapped[list["Finding"]] = relationship("Finding", back_populates="rule")


# ── Finding ───────────────────────────────────────────────────────────────────

class Finding(Base):
    """A detected security misconfiguration, linked to the rule that produced it."""
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(64), ForeignKey("rules.id"), nullable=False, index=True)

    # Connector attribution
    connector_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey(_FK_CONNECTOR), index=True)
    connector_name: Mapped[str | None] = mapped_column(String(256))

    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))           # user | repository | org
    resource_identifier: Mapped[str] = mapped_column(String(512), nullable=False)  # repo name / username / org name
    resource_name: Mapped[str | None] = mapped_column(String(512))

    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    # open | resolved | false_positive | accepted_risk
    justification: Mapped[str | None] = mapped_column(Text)         # required for false_positive / accepted_risk
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    first_detected: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_detected: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scan_run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("scan_runs.id"), index=True)

    # Ollama contextual remediation + impact (populated by POST /findings/{id}/remediate)
    ollama_remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_factor: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.5)
    generated_remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_source: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "static" | "ollama"
    impact_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_source: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "ollama" | "static"

    # LLM analysis (populated on-demand by LLM judge)
    llm_severity: Mapped[str | None] = mapped_column(String(16))
    llm_severity_reasoning: Mapped[str | None] = mapped_column(Text)
    llm_exploitability: Mapped[str | None] = mapped_column(Text)
    llm_remediation: Mapped[str | None] = mapped_column(Text)
    llm_confidence: Mapped[float | None] = mapped_column(Float)
    llm_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rule: Mapped["Rule"] = relationship("Rule", back_populates="findings")


# ── ComplianceSnapshot ────────────────────────────────────────────────────────

class ComplianceSnapshot(Base):
    """Point-in-time compliance score per platform × framework, taken after each sync."""
    __tablename__ = "compliance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    framework: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # CIS | SOC2 | ISO27001 | NIST-CSF
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    total_rules: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_rules: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rules: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    scan_run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("scan_runs.id"), nullable=True, index=True)


# ── ComplianceReport ──────────────────────────────────────────────────────────

class ComplianceReport(Base):
    """Generated compliance report with optional AI narrative."""
    __tablename__ = "compliance_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    framework: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    total_rules: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_rules: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rules: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="complete")
    findings_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    report_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    platforms_assessed: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    frameworks_assessed: Mapped[list | None] = mapped_column(JSONB, nullable=True)


# ── ActivityLog ───────────────────────────────────────────────────────────────

class ActivityLog(Base):
    """Audit/activity log entry fetched from a SaaS connector during sync."""
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey(_FK_CONNECTOR, ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(320), index=True)
    action: Mapped[str] = mapped_column(String(256), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(512))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
