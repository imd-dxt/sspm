"""
/rules  –  manage and execute detection rules.
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.models import Rule
from database.session import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/rules", tags=["rules"])


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
