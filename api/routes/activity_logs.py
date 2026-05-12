"""
/activity-logs — View SaaS platform activity and audit log entries.

Endpoints:
  GET /activity-logs          – paginated list with platform/actor/action filters
  GET /activity-logs/summary  – counts grouped by platform and action
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import ActivityLog
from database.session import get_db

router = APIRouter(prefix="/activity-logs", tags=["activity-logs"])

DB = Annotated[Session, Depends(get_db)]


@router.get("/summary")
def get_activity_summary(db: DB) -> dict[str, Any]:
    """Return activity counts grouped by platform."""
    by_platform = dict(
        db.execute(
            select(ActivityLog.platform, func.count(ActivityLog.id))
            .group_by(ActivityLog.platform)
        ).all()
    )
    total = db.execute(select(func.count(ActivityLog.id))).scalar() or 0
    return {
        "total": total,
        "by_platform": by_platform,
    }


@router.get("/")
def list_activity_logs(
    db: DB,
    platform: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    connector_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """
    List activity log entries with optional filters.

    - platform: filter by SaaS platform name (e.g. github, entraid)
    - actor: filter by actor email or username (partial match)
    - action: filter by action type (partial match)
    - connector_id: filter by specific connector UUID
    """
    q = select(ActivityLog).order_by(ActivityLog.timestamp.desc())

    if platform:
        q = q.where(ActivityLog.platform == platform)
    if connector_id:
        q = q.where(ActivityLog.connector_id == connector_id)
    if actor:
        q = q.where(ActivityLog.actor.ilike(f"%{actor}%"))
    if action:
        q = q.where(ActivityLog.action.ilike(f"%{action}%"))

    q = q.offset(offset).limit(limit)
    rows: list[ActivityLog] = list(db.execute(q).scalars())

    return [_log_to_dict(r) for r in rows]


def _log_to_dict(log: ActivityLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "connector_id": str(log.connector_id),
        "platform": log.platform,
        "actor": log.actor,
        "action": log.action,
        "resource": log.resource,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
    }
