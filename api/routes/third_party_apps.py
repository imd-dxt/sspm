"""
/third-party-apps  –  OAuth apps, GitHub Apps, service principals, and other
third-party integrations detected across connected platforms.

The endpoint surfaces apps by querying the findings table for resource_types
that represent third-party app objects (oauth_app, github_app, service_principal,
app_registration, connected_app, marketplace_app) and groups them by connector.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from database.models import Connector, Finding
from database.session import get_db

router = APIRouter(prefix="/third-party-apps", tags=["third-party-apps"])
DB = Annotated[Session, Depends(get_db)]

# Resource types that represent third-party app objects
_APP_RESOURCE_TYPES = {
    "oauth_app",
    "github_app",
    "service_principal",
    "app_registration",
    "connected_app",
    "marketplace_app",
    "integration",
}

# Category keywords that hint at third-party app findings
_APP_CATEGORY_KEYWORDS = ["oauth", "app", "integration", "third_party", "service_principal"]


class ThirdPartyApp(BaseModel):
    id: str
    name: str
    resource_type: str
    platform: str
    connector_id: str | None
    connector_name: str | None
    findings_count: int
    open_findings: int
    highest_severity: str | None
    first_seen: str | None
    last_seen: str | None


class ThirdPartyAppSummary(BaseModel):
    total_apps: int
    risky_apps: int   # apps with at least one open critical/high finding
    connectors_scanned: int
    apps: list[ThirdPartyApp]


@router.get("/", response_model=ThirdPartyAppSummary)
def list_third_party_apps(db: DB) -> ThirdPartyAppSummary:
    """
    Return all third-party apps detected across connected platforms.
    Apps are derived from findings whose resource_type indicates an app object,
    or whose category keyword indicates OAuth / integration activity.
    """
    # Build category filter
    category_filters = [
        Finding.category.ilike(f"%{kw}%") for kw in _APP_CATEGORY_KEYWORDS
    ]
    resource_type_filters = [
        Finding.resource_type == rt for rt in _APP_RESOURCE_TYPES
    ]

    rows = (
        db.query(
            Finding.resource_identifier,
            Finding.resource_type,
            Finding.platform,
            Finding.connector_id,
            Finding.connector_name,
            func.count(Finding.id).label("findings_count"),
            func.sum(
                case((Finding.status == "open", 1), else_=0)
            ).label("open_findings"),
            func.min(Finding.first_detected).label("first_seen"),
            func.max(Finding.last_detected).label("last_seen"),
        )
        .filter(
            or_(*resource_type_filters, *category_filters)
        )
        .group_by(
            Finding.resource_identifier,
            Finding.resource_type,
            Finding.platform,
            Finding.connector_id,
            Finding.connector_name,
        )
        .all()
    )

    # For each app, find the highest open severity
    severity_order = ["critical", "high", "medium", "low", "info"]

    apps: list[ThirdPartyApp] = []
    for row in rows:
        # Query highest severity open finding for this resource
        sev_row = (
            db.query(Finding.severity)
            .filter(
                Finding.resource_identifier == row.resource_identifier,
                Finding.platform == row.platform,
                Finding.status == "open",
                or_(*resource_type_filters, *category_filters),
            )
            .all()
        )
        severities = [r.severity for r in sev_row]
        highest = None
        for s in severity_order:
            if s in severities:
                highest = s
                break

        open_count = 0
        try:
            open_count = int(row.open_findings or 0)
        except (TypeError, ValueError):
            pass

        apps.append(
            ThirdPartyApp(
                id=f"{row.platform}:{row.resource_identifier}",
                name=row.resource_identifier,
                resource_type=row.resource_type or "app",
                platform=row.platform,
                connector_id=row.connector_id,
                connector_name=row.connector_name,
                findings_count=row.findings_count,
                open_findings=open_count,
                highest_severity=highest,
                first_seen=row.first_seen.isoformat() if row.first_seen else None,
                last_seen=row.last_seen.isoformat() if row.last_seen else None,
            )
        )

    risky = sum(1 for a in apps if a.highest_severity in ("critical", "high"))
    connector_ids = {a.connector_id for a in apps if a.connector_id}

    return ThirdPartyAppSummary(
        total_apps=len(apps),
        risky_apps=risky,
        connectors_scanned=db.query(Connector).filter(Connector.connection_ok == True).count(),  # noqa: E712
        apps=apps,
    )
