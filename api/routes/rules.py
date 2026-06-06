"""
/rules  –  manage and execute detection rules.

Also exposes Custom Policy creation — admin-defined rules tailored to the
organisation's own risk appetite and complex-app context, alongside the
shipped CIS / SOC2 / ISO / NIST rules.
"""
import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.models import Rule
from database.session import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/rules", tags=["rules"])


# ── Custom Policy schemas ─────────────────────────────────────────────────────

_ALLOWED_PLATFORMS = {"github", "jira", "salesforce", "entraid", "cross-platform"}
_ALLOWED_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_ALLOWED_FRAMEWORKS = {"CIS", "SOC2", "ISO27001", "NIST-CSF"}


class CustomRuleCreate(BaseModel):
    name:        str  = Field(..., min_length=3, max_length=256)
    platform:    str  = Field(..., description="github | jira | salesforce | entraid | cross-platform")
    severity:    str  = Field(..., description="critical | high | medium | low | info")
    category:    str  = Field("custom", max_length=64)
    description: str  = Field("", max_length=2000)
    remediation: str  = Field("", max_length=4000)
    referentials: list[str] = Field(default_factory=list, description="Frameworks this rule contributes to")
    compliance_mapping: list[dict[str, str]] = Field(default_factory=list, description="e.g. [{'SOC2-TSC': 'CC6.1'}]")
    detection_query: str = Field("", description="Optional Cypher query — leave empty for policy-only rules")


class CustomRuleUpdate(BaseModel):
    name:        str | None = None
    severity:    str | None = None
    category:    str | None = None
    description: str | None = None
    remediation: str | None = None
    referentials: list[str] | None = None
    compliance_mapping: list[dict[str, str]] | None = None
    detection_query: str | None = None
    is_active:   bool | None = None


@router.get("/", response_model=list[dict])
def list_rules(
    platform: str | None = Query(None),
    severity: str | None = Query(None),
    referential: str | None = Query(None, description="Filter by standard, e.g. CIS, ISO27001, NIST"),
    is_active: bool = Query(True),
    db: Session = Depends(get_db),
) -> list[dict]:
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    q = db.query(Rule).filter(Rule.is_active == is_active)
    if platform:
        q = q.filter(Rule.platform == platform)
    if severity:
        q = q.filter(Rule.severity == severity)
    if referential:
        # JSONB array contains the referential string
        q = q.filter(Rule.referentials.cast(JSONB).contains([referential]))
    rules = q.order_by(Rule.severity, Rule.id).all()
    return [_rule_to_dict(r) for r in rules]


@router.get("/{rule_id}", response_model=dict)
def get_rule(rule_id: str, db: Session = Depends(get_db)) -> dict:
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found")
    return _rule_to_dict(rule, include_query=True)


@router.post("/reload", response_model=dict[str, Any])
def reload_rules(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Reload all rule YAML files from disk into the DB (upsert). Safe to call repeatedly."""
    import os
    from pathlib import Path
    from core.rules_loader import RulesLoader

    rules_dir = Path(os.getenv("RULES_DIR", "/app/rules"))
    if not rules_dir.exists():
        raise HTTPException(status_code=500, detail=f"Rules directory not found: {rules_dir}")

    loader = RulesLoader(db)
    totals: dict[str, Any] = {"inserted": 0, "updated": 0, "errors": 0, "files": []}
    for yaml_file in sorted(rules_dir.glob("*.yaml")):
        try:
            result = loader.load_from_yaml(str(yaml_file))
            totals["inserted"] += result["inserted"]
            totals["updated"] += result["updated"]
            totals["errors"] += result["errors"]
            totals["files"].append({"file": yaml_file.name, **result})
        except Exception as exc:
            totals["errors"] += 1
            totals["files"].append({"file": yaml_file.name, "error": str(exc)})
    return totals


@router.post("/run", response_model=dict[str, Any])
def run_all_rules(
    platform: str | None = Query(None, description="Filter by platform, e.g. 'github'"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Execute all active rules and return a summary of findings."""
    from core.graph_manager import GraphManager
    from core.rules_engine import RulesEngine

    gm = GraphManager()
    try:
        engine = RulesEngine(db=db, graph=gm)
        return engine.run_all_rules(platform=platform)
    finally:
        gm.close()


# ── Custom Policies (admin-defined rules) ─────────────────────────────────────

def _next_custom_id(db: Session) -> str:
    """Return the next unused CUSTOM-### identifier."""
    existing = (
        db.query(Rule.id)
        .filter(Rule.id.like("CUSTOM-%"))
        .all()
    )
    used: set[int] = set()
    for (rid,) in existing:
        m = re.match(r"^CUSTOM-(\d+)$", rid)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"CUSTOM-{n:03d}"


@router.post("/custom", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_custom_policy(
    payload: Annotated[CustomRuleCreate, Body(...)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """
    Create a custom detection policy tailored to your risk profile.

    Shipped CIS/SOC2/ISO/NIST rules are one-size-fits-all baselines. Custom
    policies let admins encode org-specific requirements (e.g. "no repo named
    *production* can be public", "external users with admin in our Salesforce
    sandbox", "third-party apps with full-access scopes on critical Jira
    projects") that the baseline rules can't express.
    """
    if payload.platform not in _ALLOWED_PLATFORMS:
        raise HTTPException(
            status_code=422,
            detail=f"platform must be one of {sorted(_ALLOWED_PLATFORMS)}",
        )
    if payload.severity not in _ALLOWED_SEVERITIES:
        raise HTTPException(
            status_code=422,
            detail=f"severity must be one of {sorted(_ALLOWED_SEVERITIES)}",
        )
    invalid = [r for r in payload.referentials if r not in _ALLOWED_FRAMEWORKS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"unknown referential(s) {invalid}; allowed: {sorted(_ALLOWED_FRAMEWORKS)}",
        )

    rule_id = _next_custom_id(db)
    new_rule = Rule(
        id=rule_id,
        name=payload.name.strip(),
        platform=payload.platform,
        severity=payload.severity,
        category=payload.category.strip() or "custom",
        description=payload.description,
        remediation=payload.remediation,
        detection_query=payload.detection_query,
        query_type="cypher" if payload.detection_query else "policy",
        resource_id_field="resource",
        compliance_mapping=payload.compliance_mapping or [],
        referentials=payload.referentials or ["CIS"],
        is_active=True,
    )
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)
    log.info("custom_policy_created", extra={"id": rule_id, "name": payload.name, "platform": payload.platform})
    return _rule_to_dict(new_rule, include_query=True)


@router.patch("/custom/{rule_id}", response_model=dict)
def update_custom_policy(
    rule_id: str,
    payload: Annotated[CustomRuleUpdate, Body(...)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Edit an existing custom policy. Only CUSTOM-* rules can be edited via API."""
    if not rule_id.startswith("CUSTOM-"):
        raise HTTPException(status_code=403, detail="Only custom (CUSTOM-*) rules can be edited via this endpoint.")
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found")

    if payload.name is not None: rule.name = payload.name.strip()
    if payload.severity is not None:
        if payload.severity not in _ALLOWED_SEVERITIES:
            raise HTTPException(status_code=422, detail="invalid severity")
        rule.severity = payload.severity
    if payload.category is not None:    rule.category = payload.category.strip() or "custom"
    if payload.description is not None: rule.description = payload.description
    if payload.remediation is not None: rule.remediation = payload.remediation
    if payload.referentials is not None:
        invalid = [r for r in payload.referentials if r not in _ALLOWED_FRAMEWORKS]
        if invalid:
            raise HTTPException(status_code=422, detail=f"unknown referential(s) {invalid}")
        rule.referentials = payload.referentials
    if payload.compliance_mapping is not None:
        rule.compliance_mapping = payload.compliance_mapping
    if payload.detection_query is not None:
        rule.detection_query = payload.detection_query
        rule.query_type = "cypher" if payload.detection_query else "policy"
    if payload.is_active is not None:
        rule.is_active = payload.is_active

    db.commit()
    db.refresh(rule)
    return _rule_to_dict(rule, include_query=True)


@router.delete("/custom/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_policy(rule_id: str, db: Annotated[Session, Depends(get_db)]) -> None:
    """Soft-delete a custom policy (sets is_active=false)."""
    if not rule_id.startswith("CUSTOM-"):
        raise HTTPException(status_code=403, detail="Only custom (CUSTOM-*) rules can be deleted via this endpoint.")
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found")
    rule.is_active = False
    db.commit()


@router.post("/{rule_id}/run", response_model=list[dict])
def run_single_rule(rule_id: str, db: Session = Depends(get_db)) -> list[dict]:
    """Execute a single rule and return its current open findings."""
    from core.graph_manager import GraphManager
    from core.rules_engine import RulesEngine

    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found")

    gm = GraphManager()
    try:
        engine = RulesEngine(db=db, graph=gm)
        findings = engine.run_rule(rule_id)
        return [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "resource_identifier": f.resource_identifier,
                "severity": f.severity,
                "status": f.status,
                "first_detected": f.first_detected.isoformat(),
                "last_detected": f.last_detected.isoformat(),
            }
            for f in findings
        ]
    finally:
        gm.close()


def _infer_referentials(rule: "Rule") -> list[str]:
    """Infer referential tags from rule metadata when not explicitly set."""
    refs: list[str] = []
    if rule.cis_control:
        refs.append("CIS")
    if rule.compliance_mapping:
        for c in rule.compliance_mapping:
            if not isinstance(c, str):
                continue
            cu = c.upper()
            if cu.startswith("ISO") and "ISO27001" not in refs:
                refs.append("ISO27001")
            elif cu.startswith("NIST") and "NIST" not in refs:
                refs.append("NIST")
            elif cu.startswith("SOC") and "SOC2" not in refs:
                refs.append("SOC2")
    return refs or ["CIS"]  # default fallback


def _rule_to_dict(rule: "Rule", include_query: bool = False) -> dict:
    d = {
        "id": rule.id,
        "name": rule.name,
        "platform": rule.platform,
        "cis_control": rule.cis_control,
        "severity": rule.severity,
        "category": rule.category,
        "profile": rule.profile,
        "description": rule.description,
        "remediation": rule.remediation,
        "compliance_mapping": rule.compliance_mapping or [],
        "referentials": rule.referentials or _infer_referentials(rule),
        "is_active": rule.is_active,
    }
    if include_query:
        d["detection_query"] = rule.detection_query
        d["query_type"] = rule.query_type
        d["rationale"] = rule.rationale
    return d
