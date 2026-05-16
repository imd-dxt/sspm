"""
/compliance  –  Compliance posture reports per standard (CIS, SOC2, ISO27001, NIST-CSF).

Endpoints:
  GET  /                  – overall report (backward-compat overview)
  GET  /scores            – current score per platform × framework
  GET  /scores/{platform} – scores filtered to one platform
  GET  /trends            – historical snapshot data
  POST /report            – generate a report with optional AI narrative
  GET  /reports           – list generated reports
  GET  /reports/{id}      – single report details
  POST /ask               – ask AI a compliance question
  POST /fix/{finding_id}  – get AI remediation suggestion for a finding
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import distinct
from sqlalchemy.orm import Session

from core.compliance_engine import FRAMEWORKS, ComplianceEngine, _parse_mappings
from database.models import ComplianceReport as DbReport
from database.models import ComplianceSnapshot, Finding, Rule
from database.session import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/compliance", tags=["compliance"])
DB = Annotated[Session, Depends(get_db)]

# ── Control name registry ─────────────────────────────────────────────────────

_CONTROL_NAMES: dict[str, str] = {
    "SOC2-CC6.1": "Logical and Physical Access Controls",
    "SOC2-CC6.2": "User Access Provisioning",
    "SOC2-CC6.3": "User Access Reviews",
    "SOC2-CC6.6": "Security Incident Procedures",
    "SOC2-CC7.1": "System Operation Monitoring",
    "SOC2-CC7.2": "Monitoring of System Components",
    "SOC2-CC8.1": "Change Management",
    "ISO27001-A.9.1": "Access Control Policy",
    "ISO27001-A.9.2": "User Access Management",
    "ISO27001-A.9.4": "Application and Information Access",
    "ISO27001-A.12.1": "Operational Procedures and Responsibilities",
    "ISO27001-A.12.6": "Technical Vulnerability Management",
    "ISO27001-A.14.2": "Security in Development and Support Processes",
    "NIST-CSF-PR.AC-1": "Identity and Credential Management",
    "NIST-CSF-PR.AC-4": "Access Permissions and Authorizations",
    "NIST-CSF-PR.IP-1": "Baseline Configuration",
    "NIST-CSF-PR.IP-3": "Configuration Change Control",
    "NIST-CSF-DE.CM-1": "Network Monitoring",
    "NIST-CSF-DE.CM-7": "Monitoring for Unauthorized Personnel/Connections",
}

_STD_META = {
    "CIS":      {"name": "CIS Benchmark",              "description": "Center for Internet Security Benchmarks",   "icon": "shield"},
    "SOC2":     {"name": "SOC 2 Type II",              "description": "AICPA Trust Services Criteria",             "icon": "check-circle"},
    "ISO27001": {"name": "ISO/IEC 27001:2022",         "description": "Information Security Management System",    "icon": "globe"},
    "NIST-CSF": {"name": "NIST Cybersecurity Framework", "description": "NIST CSF v1.1",                           "icon": "lock"},
}


# ── Pydantic models ───────────────────────────────────────────────────────────

class ComplianceControl(BaseModel):
    id: str
    name: str
    status: str  # pass | fail | unknown
    open_findings: int
    total_findings: int
    rules: list[str]


class ComplianceStandard(BaseModel):
    id: str
    name: str
    description: str
    score: int
    total_controls: int
    passing_controls: int
    failing_controls: int
    unknown_controls: int
    controls: list[ComplianceControl]


class OverallReport(BaseModel):
    standards: list[ComplianceStandard]
    overall_score: int
    last_updated: str | None


class PlatformScore(BaseModel):
    platform: str
    framework: str
    framework_name: str
    score: int
    total_rules: int
    passed_rules: int
    failed_rules: int


class TrendPoint(BaseModel):
    snapshot_date: str
    platform: str
    framework: str
    score: int


class GenerateReportRequest(BaseModel):
    platform: str
    framework: str
    with_ai_narrative: bool = True


class StoredReport(BaseModel):
    id: int
    platform: str
    framework: str
    score: int
    total_rules: int
    passed_rules: int
    failed_rules: int
    ai_narrative: str | None
    created_at: str


class AskRequest(BaseModel):
    question: str
    platform: str | None = None
    framework: str | None = None


class AskResponse(BaseModel):
    answer: str
    source: str  # "ollama" | "static"


class FixResponse(BaseModel):
    finding_id: int
    suggestion: str
    source: str  # "ollama" | "static"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_control_report(db: Session) -> OverallReport:
    """Build the legacy per-control overview (used by GET /)."""
    try:
        active_rules = db.query(Rule).filter(Rule.is_active.is_(True)).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"rules query failed: {exc}") from exc

    control_to_rules: dict[str, list[str]] = {}
    for rule in active_rules:
        for ctrl in _parse_mappings(rule.compliance_mapping):
            control_to_rules.setdefault(ctrl, []).append(rule.id)

    standards_out: list[ComplianceStandard] = []
    for std_id, meta in _STD_META.items():
        prefix = FRAMEWORKS[std_id]["prefix"]
        std_controls = {c: r for c, r in control_to_rules.items() if c.startswith(prefix)}

        if not std_controls:
            standards_out.append(ComplianceStandard(
                id=std_id, name=meta["name"], description=meta["description"],
                score=100, total_controls=0, passing_controls=0,
                failing_controls=0, unknown_controls=0, controls=[],
            ))
            continue

        controls_out: list[ComplianceControl] = []
        for ctrl_id, rule_ids in sorted(std_controls.items()):
            open_count = db.query(Finding).filter(Finding.rule_id.in_(rule_ids), Finding.status == "open").count()
            total_count = db.query(Finding).filter(Finding.rule_id.in_(rule_ids)).count()
            if total_count == 0:
                status = "unknown"
            elif open_count == 0:
                status = "pass"
            else:
                status = "fail"
            controls_out.append(ComplianceControl(
                id=ctrl_id, name=_CONTROL_NAMES.get(ctrl_id, ctrl_id),
                status=status, open_findings=open_count, total_findings=total_count, rules=rule_ids,
            ))

        passing = sum(1 for c in controls_out if c.status == "pass")
        failing = sum(1 for c in controls_out if c.status == "fail")
        unknown = sum(1 for c in controls_out if c.status == "unknown")
        covered = passing + failing
        score = round((passing / covered) * 100) if covered > 0 else 0
        standards_out.append(ComplianceStandard(
            id=std_id, name=meta["name"], description=meta["description"],
            score=score, total_controls=len(controls_out),
            passing_controls=passing, failing_controls=failing, unknown_controls=unknown,
            controls=controls_out,
        ))

    covered_stds = [s for s in standards_out if s.total_controls > 0]
    overall = round(sum(s.score for s in covered_stds) / len(covered_stds)) if covered_stds else 0
    return OverallReport(
        standards=standards_out,
        overall_score=overall,
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=OverallReport)
def get_compliance_overview(db: DB) -> OverallReport:
    return _build_control_report(db)


@router.get("/scores", response_model=list[PlatformScore])
def get_all_scores(db: DB) -> list[PlatformScore]:
    """Current compliance score for every platform × framework combination."""
    try:
        platforms = [row[0] for row in db.query(distinct(Rule.platform)).all()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB error: {exc}") from exc

    engine = ComplianceEngine()
    out: list[PlatformScore] = []
    for platform in platforms:
        for framework in FRAMEWORKS:
            result = engine.calculate_score(platform, framework, db)
            if result["total_rules"] > 0:
                out.append(PlatformScore(**result))
    return out


@router.get("/scores/{platform}", response_model=list[PlatformScore])
def get_scores_by_platform(platform: str, db: DB) -> list[PlatformScore]:
    """Compliance scores for a specific platform across all frameworks."""
    engine = ComplianceEngine()
    out: list[PlatformScore] = []
    for framework in FRAMEWORKS:
        result = engine.calculate_score(platform, framework, db)
        if result["total_rules"] > 0:
            out.append(PlatformScore(**result))
    return out


@router.get("/trends", response_model=list[TrendPoint])
def get_trends(
    db: DB,
    platform: str | None = Query(None),
    framework: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
) -> list[TrendPoint]:
    """Historical snapshot data for compliance trend charts."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = db.query(ComplianceSnapshot).filter(ComplianceSnapshot.snapshot_date >= cutoff)
    if platform:
        q = q.filter(ComplianceSnapshot.platform == platform)
    if framework:
        q = q.filter(ComplianceSnapshot.framework == framework)
    snaps = q.order_by(ComplianceSnapshot.snapshot_date).all()
    return [
        TrendPoint(
            snapshot_date=s.snapshot_date.isoformat(),
            platform=s.platform,
            framework=s.framework,
            score=s.score,
        )
        for s in snaps
    ]


@router.post("/report", response_model=StoredReport, status_code=201)
async def generate_report(req: GenerateReportRequest, db: DB) -> StoredReport:
    """Generate a compliance report with optional AI narrative."""
    engine = ComplianceEngine()
    result = engine.calculate_score(req.platform, req.framework, db)

    narrative: str | None = None
    if req.with_ai_narrative:
        try:
            from core.llm_ollama import _generate
            fw_name = FRAMEWORKS.get(req.framework, {}).get("name", req.framework)
            prompt = (
                f"You are a SaaS security compliance expert. Write a 3-paragraph executive summary "
                f"for a {fw_name} compliance report.\n\n"
                f"Platform: {req.platform}\n"
                f"Score: {result['score']}%\n"
                f"Total mapped rules: {result['total_rules']}\n"
                f"Passing: {result['passed_rules']}\n"
                f"Failing: {result['failed_rules']}\n\n"
                f"Paragraphs: (1) current posture, (2) key risks, (3) recommended next steps. "
                f"Be specific, concise, and professional."
            )
            narrative = await _generate(prompt)
        except Exception as exc:
            log.warning("AI narrative failed for report: %s", exc)
            narrative = (
                f"Compliance assessment for {req.platform} against {req.framework}: "
                f"score {result['score']}% ({result['passed_rules']}/{result['total_rules']} rules passing). "
                f"AI narrative unavailable — Ollama may be offline."
            )

    report = DbReport(
        platform=req.platform,
        framework=req.framework,
        score=result["score"],
        total_rules=result["total_rules"],
        passed_rules=result["passed_rules"],
        failed_rules=result["failed_rules"],
        ai_narrative=narrative,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _report_out(report)


@router.get("/reports", response_model=list[StoredReport])
def list_reports(db: DB, limit: int = Query(20, ge=1, le=100)) -> list[StoredReport]:
    reports = db.query(DbReport).order_by(DbReport.created_at.desc()).limit(limit).all()
    return [_report_out(r) for r in reports]


@router.get("/reports/{report_id}", response_model=StoredReport)
def get_report(report_id: int, db: DB) -> StoredReport:
    report = db.get(DbReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_out(report)


@router.post("/ask", response_model=AskResponse)
async def ask_compliance(req: AskRequest, db: DB) -> AskResponse:
    """Ask the AI a compliance question."""
    context_parts: list[str] = []
    if req.platform or req.framework:
        engine = ComplianceEngine()
        if req.platform and req.framework:
            result = engine.calculate_score(req.platform, req.framework, db)
            context_parts.append(
                f"Current {req.framework} score for {req.platform}: {result['score']}% "
                f"({result['passed_rules']}/{result['total_rules']} rules passing)"
            )

    ctx = "\n".join(context_parts) or "No specific platform/framework context provided."
    prompt = (
        f"You are a SaaS security compliance expert. Answer the following question concisely and accurately.\n\n"
        f"Context:\n{ctx}\n\n"
        f"Question: {req.question}\n\n"
        f"Answer (2-4 sentences, professional tone, actionable where possible):"
    )

    try:
        from core.llm_ollama import _generate
        answer = await _generate(prompt)
        return AskResponse(answer=answer, source="ollama")
    except Exception as exc:
        log.warning("AI ask failed: %s", exc)
        return AskResponse(
            answer=(
                "AI assistant is currently unavailable (Ollama may be offline). "
                "Please consult your security team or the relevant compliance framework documentation."
            ),
            source="static",
        )


@router.post("/fix/{finding_id}", response_model=FixResponse)
async def get_ai_fix(finding_id: int, db: DB) -> FixResponse:
    """Get an AI-generated remediation suggestion for a finding."""
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    rule = db.get(Rule, finding.rule_id)
    finding_dict: dict[str, Any] = {
        "id": finding.id,
        "platform": finding.platform,
        "rule_id": finding.rule_id,
        "rule_name": rule.name if rule else finding.rule_id,
        "severity": finding.severity,
        "description": finding.description,
        "resource_type": finding.resource_type,
        "resource_name": finding.resource_name,
        "resource_identifier": finding.resource_identifier,
        "category": finding.category,
        "remediation": rule.remediation if rule else "",
        "evidence": finding.evidence or {},
    }

    try:
        from core.llm_ollama import generate_remediation
        suggestion, source = await generate_remediation(finding_dict)
        return FixResponse(finding_id=finding_id, suggestion=suggestion, source=source)
    except Exception as exc:
        log.warning("AI fix failed for finding %s: %s", finding_id, exc)
        static = rule.remediation if rule else "Refer to rule documentation for remediation guidance."
        return FixResponse(finding_id=finding_id, suggestion=static, source="static")


def _report_out(r: DbReport) -> StoredReport:
    return StoredReport(
        id=r.id,
        platform=r.platform,
        framework=r.framework,
        score=r.score,
        total_rules=r.total_rules,
        passed_rules=r.passed_rules,
        failed_rules=r.failed_rules,
        ai_narrative=r.ai_narrative,
        created_at=r.created_at.isoformat(),
    )
