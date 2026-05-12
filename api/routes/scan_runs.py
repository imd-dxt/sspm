"""
/scan_runs  –  List scan runs across all connectors.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.models import ScanRun
from database.schemas import ScanRunResponse
from database.session import get_db

router = APIRouter(prefix="/scan_runs", tags=["scan-runs"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/", response_model=list[ScanRunResponse])
def list_scan_runs(db: DB) -> list[ScanRun]:
    """List all scan runs across all connectors, newest first."""
    return (
        db.query(ScanRun)
        .order_by(ScanRun.started_at.desc())
        .limit(200)
        .all()
    )
