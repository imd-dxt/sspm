"""
/genai-security — audit + policy controls for cloud-LLM calls.

Endpoints:
  GET  /genai-security/summary  – call counts, blocks, PII attempts (last 30 days)
  GET  /genai-security/logs     – paginated audit log entries
  GET  /genai-security/policy   – currently enforced policy values
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.llm_router import MAX_DEEPSEEK_PROMPT_CHARS
from database.models import GenAIAuditLog
from database.session import get_db

router = APIRouter(prefix="/genai-security", tags=["genai-security"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/summary")
def get_summary(
    db: DB,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    """Aggregate stats over the last `days` days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    base = db.query(GenAIAuditLog).filter(GenAIAuditLog.timestamp >= since)
    total      = base.count()
    blocked    = base.filter(GenAIAuditLog.blocked.is_(True)).count()
    pii_blocks = base.filter(
        GenAIAuditLog.blocked.is_(True),
        (GenAIAuditLog.pii_emails > 0)
        | (GenAIAuditLog.pii_uuids > 0)
        | (GenAIAuditLog.pii_ips > 0),
    ).count()

    by_task = dict(
        db.query(GenAIAuditLog.task, func.count(GenAIAuditLog.id))
        .filter(GenAIAuditLog.timestamp >= since)
        .group_by(GenAIAuditLog.task)
        .all()
    )
    by_provider = dict(
        db.query(GenAIAuditLog.provider, func.count(GenAIAuditLog.id))
        .filter(GenAIAuditLog.timestamp >= since)
        .group_by(GenAIAuditLog.provider)
        .all()
    )

    avg_latency = (
        db.query(func.avg(GenAIAuditLog.latency_ms))
        .filter(GenAIAuditLog.timestamp >= since, GenAIAuditLog.latency_ms.isnot(None))
        .scalar()
    )
    total_tokens_substituted = (
        db.query(func.sum(GenAIAuditLog.tokens_substituted))
        .filter(GenAIAuditLog.timestamp >= since)
        .scalar()
    ) or 0

    return {
        "window_days":              days,
        "total_calls":              total,
        "blocked_calls":            blocked,
        "blocked_for_pii":          pii_blocks,
        "calls_by_task":            by_task,
        "calls_by_provider":        by_provider,
        "avg_latency_ms":           round(avg_latency, 1) if avg_latency else 0,
        "tokens_substituted_total": int(total_tokens_substituted),
    }


@router.get("/logs")
def list_logs(
    db: DB,
    limit:  Annotated[int, Query(le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    blocked_only: bool = False,
) -> list[dict[str, Any]]:
    """Paginated audit log entries — most recent first."""
    q = db.query(GenAIAuditLog).order_by(GenAIAuditLog.timestamp.desc())
    if blocked_only:
        q = q.filter(GenAIAuditLog.blocked.is_(True))
    rows = q.offset(offset).limit(limit).all()
    return [
        {
            "id":                  r.id,
            "timestamp":           r.timestamp.isoformat() if r.timestamp else None,
            "provider":            r.provider,
            "task":                r.task,
            "model":               r.model,
            "prompt_chars":        r.prompt_chars,
            "response_chars":      r.response_chars,
            "pii_emails":          r.pii_emails,
            "pii_uuids":           r.pii_uuids,
            "pii_ips":             r.pii_ips,
            "tokens_substituted":  r.tokens_substituted,
            "blocked":             r.blocked,
            "block_reason":        r.block_reason,
            "latency_ms":          r.latency_ms,
        }
        for r in rows
    ]


@router.get("/policy")
def get_policy() -> dict[str, Any]:
    """Currently enforced policy values for cloud LLM calls."""
    return {
        "providers_allowed":          ["deepseek"],
        "max_prompt_chars":           MAX_DEEPSEEK_PROMPT_CHARS,
        "block_on_pii":               True,
        "tasks_routed_to_cloud": [
            "executive_summary", "impact_analysis",
            "exploitation_scenario", "trend_narrative",
            "roadmap_intro",
        ],
        "tasks_kept_local": [
            "remediation_steps", "finding_explanation",
            "qa_answer", "finding_anonymisation",
        ],
        "pre_send_sanitisation":      "tokenise SENSITIVE_FIELDS values + EMAIL/UUID/IP patterns",
        "audit_retention_days":       365,
    }
