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

from database.models import Connector, Finding, NormalizedEntity
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

    # Build findings-based apps, keyed by (platform, resource_identifier)
    apps_by_key: dict[tuple[str, str], ThirdPartyApp] = {}

    for row in rows:
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

        key = (row.platform, row.resource_identifier)
        apps_by_key[key] = ThirdPartyApp(
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

    # Also surface app entities from NormalizedEntity (e.g. Entra app registrations
    # that haven't triggered a finding yet — they still deserve visibility)
    entity_rows = (
        db.query(NormalizedEntity)
        .filter(NormalizedEntity.entity_type == "application")
        .all()
    )
    for ent in entity_rows:
        data = ent.data_json or {}
        name = (
            data.get("name")
            or data.get("display_name")
            or data.get("app_name")
            or ent.platform_id
        )
        key = (ent.platform, name)
        if key in apps_by_key:
            continue  # already captured via findings

        # Count findings for this entity from the findings table
        finding_rows = (
            db.query(Finding.severity, Finding.status)
            .filter(
                Finding.platform == ent.platform,
                Finding.resource_identifier == name,
            )
            .all()
        )
        total_f = len(finding_rows)
        open_f = sum(1 for f in finding_rows if f.status == "open")
        open_sevs = [f.severity for f in finding_rows if f.status == "open"]
        highest = None
        for s in severity_order:
            if s in open_sevs:
                highest = s
                break

        apps_by_key[key] = ThirdPartyApp(
            id=f"{ent.platform}:{name}",
            name=name,
            resource_type=data.get("entity_subtype") or "application",
            platform=ent.platform,
            connector_id=None,
            connector_name=None,
            findings_count=total_f,
            open_findings=open_f,
            highest_severity=highest,
            first_seen=ent.created_at.isoformat() if ent.created_at else None,
            last_seen=ent.updated_at.isoformat() if ent.updated_at else None,
        )

    apps = list(apps_by_key.values())
    risky = sum(1 for a in apps if a.highest_severity in ("critical", "high"))

    return ThirdPartyAppSummary(
        total_apps=len(apps),
        risky_apps=risky,
        connectors_scanned=db.query(Connector).filter(Connector.connection_ok == True).count(),  # noqa: E712
        apps=apps,
    )
