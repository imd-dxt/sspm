"""
/compliance  –  Compliance posture reports per standard (CIS, SOC2, ISO27001, NIST CSF).

Derives compliance status from:
  - Rules with compliance_mapping fields
  - Open findings that violate those rules

A control "passes" when zero open findings exist for its mapped rules.
A control "fails" when one or more open findings exist.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.models import Finding, Rule
from database.session import get_db

router = APIRouter(prefix="/compliance", tags=["compliance"])
DB = Annotated[Session, Depends(get_db)]

_STANDARDS: dict[str, dict] = {
    "CIS": {
        "name": "CIS Benchmark",
        "description": "Center for Internet Security Benchmarks",
        "prefix": "CIS",
        "icon": "shield",
    },
    "SOC2": {
        "name": "SOC 2 Type II",
        "description": "AICPA Trust Services Criteria",
        "prefix": "SOC2",
        "icon": "check-circle",
    },
    "ISO27001": {
        "name": "ISO/IEC 27001:2022",
        "description": "Information Security Management System",
        "prefix": "ISO27001",
        "icon": "globe",
    },
    "NIST-CSF": {
        "name": "NIST Cybersecurity Framework",
        "description": "NIST CSF v1.1",
        "prefix": "NIST-CSF",
        "icon": "lock",
    },
}

_CONTROL_NAMES: dict[str, str] = {
    # SOC 2
    "SOC2-CC6.1": "Logical and Physical Access Controls",
    "SOC2-CC6.2": "User Access Provisioning",
    "SOC2-CC6.3": "User Access Reviews",
    "SOC2-CC6.6": "Security Incident Procedures",
    "SOC2-CC7.1": "System Operation Monitoring",
    "SOC2-CC7.2": "Monitoring of System Components",
    "SOC2-CC8.1": "Change Management",
    # ISO 27001
    "ISO27001-A.9.1": "Access Control Policy",
    "ISO27001-A.9.2": "User Access Management",
    "ISO27001-A.9.4": "Application and Information Access",
    "ISO27001-A.12.1": "Operational Procedures and Responsibilities",
    "ISO27001-A.12.6": "Technical Vulnerability Management",
    "ISO27001-A.14.2": "Security in Development and Support Processes",
    # NIST CSF
    "NIST-CSF-PR.AC-1": "Identity and Credential Management",
    "NIST-CSF-PR.AC-4": "Access Permissions and Authorizations",
    "NIST-CSF-PR.IP-1": "Baseline Configuration",
    "NIST-CSF-PR.IP-3": "Configuration Change Control",
    "NIST-CSF-DE.CM-1": "Network Monitoring",
    "NIST-CSF-DE.CM-7": "Monitoring for Unauthorized Personnel/Connections",
}


class ComplianceControl(BaseModel):
    id: str
    name: str
    status: str  # "pass" | "fail" | "unknown"
    open_findings: int
    total_findings: int
    rules: list[str]


class ComplianceStandard(BaseModel):
    id: str
    name: str
    description: str
    score: int  # 0–100
    total_controls: int
    passing_controls: int
    failing_controls: int
    unknown_controls: int
    controls: list[ComplianceControl]


class ComplianceReport(BaseModel):
    standards: list[ComplianceStandard]
    overall_score: int
    last_updated: str | None


@router.get("/", response_model=ComplianceReport)
def get_compliance_report(db: DB) -> ComplianceReport:
    # Map control_id → list[rule_id]
    control_to_rules: dict[str, list[str]] = {}
    try:
        active_rules = db.query(Rule).filter(Rule.is_active.is_(True)).all()
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"rules query failed: {exc}") from exc

    for rule in active_rules:
        mappings = rule.compliance_mapping
        if not mappings:
            continue
        if isinstance(mappings, str):
            import json
            try:
                mappings = json.loads(mappings)
            except Exception:
                continue
        for control in mappings:
            if isinstance(control, str):
                control_to_rules.setdefault(control, []).append(rule.id)

    standards_out: list[ComplianceStandard] = []

    for std_id, meta in _STANDARDS.items():
        prefix = meta["prefix"]
        std_controls = {
            c: r for c, r in control_to_rules.items() if c.startswith(prefix)
        }

        if not std_controls:
            standards_out.append(
                ComplianceStandard(
                    id=std_id,
                    name=meta["name"],
                    description=meta["description"],
                    score=100,
                    total_controls=0,
                    passing_controls=0,
                    failing_controls=0,
                    unknown_controls=0,
                    controls=[],
                )
            )
            continue

        controls_out: list[ComplianceControl] = []
        for control_id, rule_ids in sorted(std_controls.items()):
            open_count = (
                db.query(Finding)
                .filter(Finding.rule_id.in_(rule_ids), Finding.status == "open")
                .count()
            )
            total_count = (
                db.query(Finding)
                .filter(Finding.rule_id.in_(rule_ids))
                .count()
            )

            if total_count == 0:
                status = "unknown"
            elif open_count == 0:
                status = "pass"
            else:
                status = "fail"

            controls_out.append(
                ComplianceControl(
                    id=control_id,
                    name=_CONTROL_NAMES.get(control_id, control_id),
                    status=status,
                    open_findings=open_count,
                    total_findings=total_count,
                    rules=rule_ids,
                )
            )

        passing = sum(1 for c in controls_out if c.status == "pass")
        failing = sum(1 for c in controls_out if c.status == "fail")
        unknown = sum(1 for c in controls_out if c.status == "unknown")
        covered = passing + failing
        score = round((passing / covered) * 100) if covered > 0 else 0

        standards_out.append(
            ComplianceStandard(
                id=std_id,
                name=meta["name"],
                description=meta["description"],
                score=score,
                total_controls=len(controls_out),
                passing_controls=passing,
                failing_controls=failing,
                unknown_controls=unknown,
                controls=controls_out,
            )
        )

    from datetime import datetime, timezone

    covered_standards = [s for s in standards_out if s.total_controls > 0]
    overall = (
        round(sum(s.score for s in covered_standards) / len(covered_standards))
        if covered_standards
        else 0
    )

    return ComplianceReport(
        standards=standards_out,
        overall_score=overall,
        last_updated=datetime.now(timezone.utc).isoformat(),
    )
