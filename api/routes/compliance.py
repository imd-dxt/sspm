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
  GET  /reports/{id}/pdf  – download report as PDF
  POST /ask               – ask AI a compliance question
  POST /fix/{finding_id}  – get AI remediation suggestion for a finding
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
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
    "ISO27001-A.9.2.6": "Removal or Adjustment of Access Rights",
    "ISO27001-A.12.1": "Operational Procedures and Responsibilities",
    "ISO27001-A.12.6": "Technical Vulnerability Management",
    "ISO27001-A.14.2": "Security in Development and Support Processes",
    "ISO27001-A.16.1": "Management of Information Security Incidents",
    "NIST-CSF-PR.AC-1": "Identity and Credential Management",
    "NIST-CSF-PR.AC-4": "Access Permissions and Authorizations",
    "NIST-CSF-PR.IP-1": "Baseline Configuration",
    "NIST-CSF-PR.IP-3": "Configuration Change Control",
    "NIST-CSF-DE.CM-1": "Network Monitoring",
    "NIST-CSF-DE.CM-7": "Monitoring for Unauthorized Personnel/Connections",
}

_STD_META = {
    "CIS":      {"name": "CIS Benchmark",               "description": "Center for Internet Security Benchmarks",   "icon": "shield"},
    "SOC2":     {"name": "SOC 2 Type II",               "description": "AICPA Trust Services Criteria",             "icon": "check-circle"},
    "ISO27001": {"name": "ISO/IEC 27001:2022",          "description": "Information Security Management System",    "icon": "globe"},
    "NIST-CSF": {"name": "NIST Cybersecurity Framework","description": "NIST CSF v1.1",                             "icon": "lock"},
}


# ── Pydantic models ───────────────────────────────────────────────────────────

class ComplianceControl(BaseModel):
    id: str
    name: str
    status: str  # pass | fail | not_applicable
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
    not_applicable_controls: int
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


# ── Control building helpers ──────────────────────────────────────────────────

def _control_status(open_count: int, total_count: int) -> str:
    if total_count == 0:
        return "not_applicable"
    if open_count == 0:
        return "pass"
    return "fail"


def _compute_score(controls: list[ComplianceControl]) -> int:
    passing = sum(1 for c in controls if c.status == "pass")
    failing = sum(1 for c in controls if c.status == "fail")
    covered = passing + failing
    # When no findings exist yet, no violations detected → treat as 100%
    return round((passing / covered) * 100) if covered > 0 else 100


def _cis_controls_from_rules(active_rules: list[Rule]) -> dict[str, list[str]]:
    """Build control_id → [rule_ids] for the CIS framework using rule IDs."""
    result: dict[str, list[str]] = {}
    for rule in active_rules:
        if not rule.id.startswith("CIS-"):
            continue
        ctrl_id = f"CIS-{rule.cis_control}" if rule.cis_control else rule.id
        result.setdefault(ctrl_id, []).append(rule.id)
    return result


def _build_control_report(db: Session) -> OverallReport:
    """Build the per-control overview."""
    try:
        active_rules = db.query(Rule).filter(Rule.is_active.is_(True)).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"rules query failed: {exc}") from exc

    # Map control → rule IDs for SOC2 / ISO27001 / NIST-CSF (via compliance_mapping)
    mapping_controls: dict[str, list[str]] = {}
    for rule in active_rules:
        for ctrl in _parse_mappings(rule.compliance_mapping):
            mapping_controls.setdefault(ctrl, []).append(rule.id)

    standards_out: list[ComplianceStandard] = []

    for std_id, meta in _STD_META.items():
        if std_id == "CIS":
            std_controls = _cis_controls_from_rules(active_rules)
        else:
            prefix = FRAMEWORKS[std_id]["prefix"]
            std_controls = {c: r for c, r in mapping_controls.items() if c.startswith(prefix)}

        if not std_controls:
            standards_out.append(ComplianceStandard(
                id=std_id, name=meta["name"], description=meta["description"],
                score=100, total_controls=0, passing_controls=0,
                failing_controls=0, not_applicable_controls=0, controls=[],
            ))
            continue

        controls_out: list[ComplianceControl] = []
        for ctrl_id, rule_ids in sorted(std_controls.items()):
            open_count = db.query(Finding).filter(
                Finding.rule_id.in_(rule_ids), Finding.status == "open"
            ).count()
            total_count = db.query(Finding).filter(Finding.rule_id.in_(rule_ids)).count()
            status = _control_status(open_count, total_count)

            # For CIS, use rule name as control name if not in registry
            name = _CONTROL_NAMES.get(ctrl_id)
            if not name and std_id == "CIS" and len(rule_ids) == 1:
                rule = next((r for r in active_rules if r.id == rule_ids[0]), None)
                name = rule.name if rule else ctrl_id
            name = name or ctrl_id

            controls_out.append(ComplianceControl(
                id=ctrl_id, name=name, status=status,
                open_findings=open_count, total_findings=total_count, rules=rule_ids,
            ))

        passing = sum(1 for c in controls_out if c.status == "pass")
        failing = sum(1 for c in controls_out if c.status == "fail")
        na = sum(1 for c in controls_out if c.status == "not_applicable")
        score = _compute_score(controls_out)

        standards_out.append(ComplianceStandard(
            id=std_id, name=meta["name"], description=meta["description"],
            score=score, total_controls=len(controls_out),
            passing_controls=passing, failing_controls=failing,
            not_applicable_controls=na, controls=controls_out,
        ))

    covered_stds = [s for s in standards_out if s.total_controls > 0]
    overall = round(sum(s.score for s in covered_stds) / len(covered_stds)) if covered_stds else 100
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
    try:
        platforms = [row[0] for row in db.query(distinct(Rule.platform)).all()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB error: {exc}") from exc

    engine = ComplianceEngine()
    return [
        PlatformScore(**engine.calculate_score(p, f, db))
        for p in platforms
        for f in FRAMEWORKS
        if engine.calculate_score(p, f, db)["total_rules"] > 0
    ]


@router.get("/scores/{platform}", response_model=list[PlatformScore])
def get_scores_by_platform(platform: str, db: DB) -> list[PlatformScore]:
    engine = ComplianceEngine()
    return [
        PlatformScore(**engine.calculate_score(platform, f, db))
        for f in FRAMEWORKS
        if engine.calculate_score(platform, f, db)["total_rules"] > 0
    ]


@router.get("/trends", response_model=list[TrendPoint])
def get_trends(
    db: DB,
    platform: str | None = Query(None),
    framework: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
) -> list[TrendPoint]:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = db.query(ComplianceSnapshot).filter(ComplianceSnapshot.snapshot_date >= cutoff)
    if platform:
        q = q.filter(ComplianceSnapshot.platform == platform)
    if framework:
        q = q.filter(ComplianceSnapshot.framework == framework)
    return [
        TrendPoint(
            snapshot_date=s.snapshot_date.isoformat(),
            platform=s.platform,
            framework=s.framework,
            score=s.score,
        )
        for s in q.order_by(ComplianceSnapshot.snapshot_date).all()
    ]


@router.post("/report", response_model=StoredReport, status_code=201)
async def generate_report(req: GenerateReportRequest, db: DB) -> StoredReport:
    engine = ComplianceEngine()
    result = engine.calculate_score(req.platform, req.framework, db)

    narrative: str | None = None
    if req.with_ai_narrative:
        try:
            from core.llm_ollama import _generate
            fw_name = FRAMEWORKS.get(req.framework, {}).get("name", req.framework)
            prompt = (
                f"You are a SaaS security compliance expert. Write a concise 3-paragraph executive summary "
                f"for a {fw_name} compliance report.\n\n"
                f"Platform: {req.platform} | Score: {result['score']}% | "
                f"Passing: {result['passed_rules']}/{result['total_rules']} rules | "
                f"Failing: {result['failed_rules']}\n\n"
                f"Paragraphs: (1) current posture, (2) key risks, (3) recommended next steps. "
                f"Professional and actionable."
            )
            narrative = await _generate(prompt)
        except Exception as exc:
            log.warning("AI narrative failed: %s", exc)
            fw_name = FRAMEWORKS.get(req.framework, {}).get("name", req.framework)
            narrative = (
                f"{fw_name} compliance assessment for {req.platform}: "
                f"score {result['score']}% — {result['passed_rules']}/{result['total_rules']} rules passing. "
                f"AI narrative unavailable (Ollama may be offline or still starting up)."
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


@router.get("/reports/{report_id}/pdf")
def download_report_pdf(report_id: int, db: DB) -> Response:
    """Download a compliance report as a PDF file."""
    report = db.get(DbReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    pdf_bytes = _build_pdf(report)
    filename = f"compliance_{report.platform}_{report.framework}_{report_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/ask", response_model=AskResponse)
async def ask_compliance(req: AskRequest, db: DB) -> AskResponse:
    context_parts: list[str] = []
    if req.platform and req.framework:
        engine = ComplianceEngine()
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
        # Provide a useful static fallback based on the question
        answer = _static_compliance_answer(req.question)
        return AskResponse(answer=answer, source="static")


@router.post("/fix/{finding_id}", response_model=FixResponse)
async def get_ai_fix(finding_id: int, db: DB) -> FixResponse:
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


# ── PDF builder ───────────────────────────────────────────────────────────────

def _build_pdf(report: DbReport) -> bytes:
    try:
        from fpdf import FPDF  # type: ignore[import]
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF library not installed. Run: pip install fpdf2")

    fw_name = FRAMEWORKS.get(report.framework, {}).get("name", report.framework)
    score_color = (34, 197, 94) if report.score >= 75 else (234, 179, 8) if report.score >= 50 else (239, 68, 68)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Header
    pdf.set_fill_color(17, 24, 39)
    pdf.rect(0, 0, 210, 32, "F")
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(14, 10)
    pdf.cell(0, 8, "SSPM Compliance Report", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(14, 20)
    pdf.cell(0, 6, f"{fw_name}  |  Platform: {report.platform}  |  Generated: {report.created_at.strftime('%Y-%m-%d %H:%M UTC')}")

    # Score section
    pdf.set_xy(14, 40)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Compliance Score", ln=True)

    pdf.set_font("Helvetica", "B", 36)
    pdf.set_text_color(*score_color)
    pdf.set_xy(14, 50)
    pdf.cell(50, 16, f"{report.score}%", ln=False)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.set_xy(70, 54)
    pdf.multi_cell(0, 5,
        f"Total rules: {report.total_rules}\n"
        f"Passing:     {report.passed_rules}\n"
        f"Failing:     {report.failed_rules}"
    )

    # AI narrative
    if report.ai_narrative:
        pdf.set_xy(14, 80)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Executive Summary", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(182, 5, report.ai_narrative)

    # Footer
    pdf.set_xy(14, -20)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, f"Generated by SSPM  |  {fw_name}  |  {report.platform}", align="C")

    return bytes(pdf.output())


# ── Static fallback answers ───────────────────────────────────────────────────

_STATIC_ANSWERS: list[tuple[list[str], str]] = [
    (
        ["mfa", "two-factor", "2fa", "multi-factor"],
        "To enforce MFA in your GitHub organization: go to Organization Settings → Authentication security → "
        "enable 'Require two-factor authentication for everyone'. Members who haven't enabled MFA will be "
        "removed from the org. Give users 72 hours notice and communicate via email before enabling."
    ),
    (
        ["branch protection", "protected branch"],
        "Enable branch protection via Settings → Branches → Add rule. Key settings: require pull requests "
        "before merging, require 2 approvals, dismiss stale reviews, require signed commits, and enable "
        "'Do not allow bypassing the above settings' for administrators."
    ),
    (
        ["soc2", "soc 2", "cc6", "trust services"],
        "SOC 2 CC6 (Logical Access Controls) requires restricting system access to authorized users. "
        "Key controls: enforce MFA, review access quarterly, terminate access upon offboarding, "
        "and ensure branch protection rules prevent unauthorized code changes."
    ),
    (
        ["cis", "cis benchmark", "cis github"],
        "The CIS GitHub Benchmark covers 5 areas: code changes (branch protection), repository management, "
        "contribution access (MFA, admin count), third-party apps, and organization settings. "
        "Priority Level 1 controls should be implemented first."
    ),
    (
        ["iso27001", "iso 27001", "a.9", "access control"],
        "ISO 27001 A.9 (Access Control) requires a formal access control policy, user provisioning "
        "procedures, regular access reviews, and removal of access rights on departure. "
        "Map your GitHub org permissions and branch protection rules to these controls."
    ),
    (
        ["nist", "nist csf", "pr.ac"],
        "NIST CSF PR.AC (Access Control) requires managing identities and credentials, controlling "
        "access permissions, and protecting physical/remote access. For GitHub: enforce MFA, "
        "use least-privilege access, and audit admin accounts regularly."
    ),
    (
        ["admin", "organization admin", "org admin"],
        "CIS GH-1.3.3 requires at least 2 organization admins to prevent single point of failure. "
        "To add an admin: Organization Settings → People → select member → Change role to Owner. "
        "Ensure all admins have MFA enabled."
    ),
    (
        ["score", "improve", "remediation", "fix"],
        "To improve your compliance score: (1) start with critical/high findings in the Remediation tab, "
        "(2) use 'Get AI fix' for step-by-step guidance, (3) prioritize controls that affect multiple "
        "frameworks simultaneously (e.g., MFA fixes CIS + SOC2 + NIST at once)."
    ),
]


def _static_compliance_answer(question: str) -> str:
    q_lower = question.lower()
    for keywords, answer in _STATIC_ANSWERS:
        if any(kw in q_lower for kw in keywords):
            return answer
    return (
        "For compliance guidance, consult the relevant framework documentation: "
        "CIS GitHub Benchmark (cisecurity.org), SOC 2 Trust Services Criteria (aicpa.org), "
        "ISO 27001 (iso.org), or NIST CSF (nist.gov). "
        "The AI assistant will provide detailed answers once Ollama is running — check that the "
        "ollama container is healthy with: docker logs sspm_ollama"
    )


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
