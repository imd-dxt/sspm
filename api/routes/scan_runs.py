"""
/scan_runs  –  List scan runs across all connectors.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.models import ScanRun
from database.schemas import ScanRunResponse
from database.session import get_db

router = APIRouter(prefix="/scan_runs", tags=["scan-runs"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/", response_model=list[ScanRunResponse])
def list_scan_runs(
    db: DB,
    connector_id: Annotated[str | None, Query()] = None,
) -> list[ScanRun]:
    """List scan runs, optionally filtered by connector_id, newest first."""
    q = db.query(ScanRun)
    if connector_id:
        q = q.filter(ScanRun.connector_id == connector_id)
    return q.order_by(ScanRun.started_at.desc()).limit(200).all()
