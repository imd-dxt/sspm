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

import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from core.compliance_engine import FRAMEWORKS, ComplianceEngine, _parse_mappings
from database.models import ComplianceReport as DbReport
from database.models import ComplianceSnapshot, Connector, Finding, NormalizedEntity, Rule
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

def _control_status(open_count: int, total_count: int, platform_scanned: bool) -> str:
    """
    Determine control status.

    The findings table only stores violations — it never stores a "no violation found" record.
    So total_count==0 means either:
      (a) the platform was scanned and the rule found zero violations → PASS
      (b) the platform has never been scanned → NOT APPLICABLE

    We distinguish (a) vs (b) by checking whether any findings exist for the rule's platform.
    """
    if total_count > 0:
        return "pass" if open_count == 0 else "fail"
    return "pass" if platform_scanned else "not_applicable"


def _compute_score(controls: list[ComplianceControl]) -> int:
    passing = sum(1 for c in controls if c.status == "pass")
    failing = sum(1 for c in controls if c.status == "fail")
    covered = passing + failing
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

    # Platforms that have been scanned (have at least one finding)
    try:
        scanned_platforms: set[str] = {
            row[0] for row in db.query(distinct(Finding.platform)).all()
        }
    except Exception:
        scanned_platforms = set()

    # Build a lookup: rule_id → platform (for scanned-platform checks)
    rule_platform: dict[str, str] = {r.id: r.platform for r in active_rules}

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

            # A control is "scanned" if any of its rules run on a platform that has findings
            ctrl_platforms = {rule_platform.get(rid, "") for rid in rule_ids}
            platform_scanned = bool(ctrl_platforms & scanned_platforms)
            status = _control_status(open_count, total_count, platform_scanned)

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

    # Collect failing rules for AI context and PDF remediation section
    failing_rules_info: list[dict] = []
    try:
        all_rules = db.query(Rule).filter(Rule.platform == req.platform, Rule.is_active.is_(True)).all()
        if req.framework == "CIS":
            fw_rules = [r for r in all_rules if r.id.startswith("CIS-")]
        else:
            prefix = FRAMEWORKS.get(req.framework, {}).get("prefix", "")
            fw_rules = [r for r in all_rules if any(m.startswith(prefix) for m in _parse_mappings(r.compliance_mapping))]
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for rule in fw_rules:
            open_count = db.query(Finding).filter(
                Finding.rule_id == rule.id, Finding.platform == req.platform, Finding.status == "open"
            ).count()
            if open_count > 0:
                failing_rules_info.append({
                    "name": rule.name,
                    "severity": rule.severity or "medium",
                    "category": rule.category or "General",
                    "remediation": rule.remediation or "",
                    "open_count": open_count,
                })
        failing_rules_info.sort(key=lambda r: sev_order.get(r["severity"].lower(), 99))
    except Exception as exc:
        log.warning("generate_report: could not fetch failing rules: %s", exc)

    narrative: str | None = None
    if req.with_ai_narrative:
        try:
            from core.llm_ollama import _generate
            fw_name = FRAMEWORKS.get(req.framework, {}).get("name", req.framework)
            failing_ctx = "\n".join(
                f"- {r['name']} ({r['severity']}): {r['open_count']} open finding(s)"
                for r in failing_rules_info[:5]
            ) or "None — all controls passing."
            prompt = (
                f"You are a GRC (Governance, Risk, Compliance) expert. Write a concise 2-paragraph executive "
                f"summary for a {fw_name} compliance report.\n\n"
                f"Platform: {req.platform} | Score: {result['score']}% | "
                f"Passing: {result['passed_rules']}/{result['total_rules']} rules | "
                f"Failing: {result['failed_rules']}\n\n"
                f"Top failing controls:\n{failing_ctx}\n\n"
                f"Paragraph 1: Current {fw_name} posture and audit readiness. "
                f"Paragraph 2: Priority remediation actions and GRC risk impact. "
                f"Professional tone, under 120 words total, no bullet points."
            )
            narrative = await asyncio.wait_for(_generate(prompt), timeout=28.0)
        except (Exception, asyncio.TimeoutError) as exc:
            log.warning("AI narrative failed: %s", exc)
            fw_name = FRAMEWORKS.get(req.framework, {}).get("name", req.framework)
            narrative = _professional_narrative(
                fw_name, req.platform, result["score"],
                result["passed_rules"], result["total_rules"],
                result["failed_rules"], failing_rules_info,
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

    # Fetch failing rules for PDF remediation + heatmap sections
    failing_rules_info: list[dict] = []
    try:
        all_rules = db.query(Rule).filter(Rule.platform == report.platform, Rule.is_active.is_(True)).all()
        if report.framework == "CIS":
            fw_rules = [r for r in all_rules if r.id.startswith("CIS-")]
        else:
            prefix = FRAMEWORKS.get(report.framework, {}).get("prefix", "")
            fw_rules = [r for r in all_rules if any(m.startswith(prefix) for m in _parse_mappings(r.compliance_mapping))]
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for rule in fw_rules:
            open_count = db.query(Finding).filter(
                Finding.rule_id == rule.id, Finding.platform == report.platform, Finding.status == "open"
            ).count()
            if open_count > 0:
                failing_rules_info.append({
                    "name": rule.name,
                    "severity": rule.severity or "medium",
                    "category": rule.category or "General",
                    "remediation": rule.remediation or "",
                    "open_count": open_count,
                })
        failing_rules_info.sort(key=lambda r: sev_order.get(r["severity"].lower(), 99))
    except Exception as exc:
        log.warning("download_report_pdf: could not fetch failing rules: %s", exc)

    pdf_bytes = _build_pdf(report, failing_rules_info)
    filename = f"compliance_{report.platform}_{report.framework}_{report_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/ask", response_model=AskResponse)
async def ask_compliance(req: AskRequest, db: DB) -> AskResponse:
    ctx_lines: list[str] = []

    # ── Workspace context: connected platforms ──────────────────────────────────
    try:
        connectors = db.query(Connector).all()
        connected = [c.platform_name for c in connectors if c.connection_ok]
        all_platforms = [c.platform_name for c in connectors]
        if connected:
            ctx_lines.append(f"Connected platforms (healthy): {', '.join(connected)}")
        elif all_platforms:
            ctx_lines.append(f"Configured platforms: {', '.join(all_platforms)}")
    except Exception as exc:
        log.warning("ask: could not fetch connectors: %s", exc)

    # ── Workspace context: open findings by severity ────────────────────────────
    try:
        sev_totals = (
            db.query(Finding.severity, func.count(Finding.id))
            .filter(Finding.status == "open")
            .group_by(Finding.severity)
            .all()
        )
        if sev_totals:
            sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            sev_sorted = sorted(sev_totals, key=lambda x: sev_order.get(x[0] or "low", 99))
            sev_str = ", ".join(f"{sev}: {cnt}" for sev, cnt in sev_sorted)
            total_open = sum(cnt for _, cnt in sev_totals)
            ctx_lines.append(f"Open findings: {total_open} total ({sev_str})")
        else:
            ctx_lines.append("Open findings: 0 (all controls passing or no scan yet)")
    except Exception as exc:
        log.warning("ask: could not fetch findings summary: %s", exc)

    # ── Workspace context: identity counts per platform ─────────────────────────
    try:
        user_counts = (
            db.query(NormalizedEntity.platform, func.count(NormalizedEntity.id))
            .filter(NormalizedEntity.entity_type == "user")
            .group_by(NormalizedEntity.platform)
            .all()
        )
        app_counts = (
            db.query(NormalizedEntity.platform, func.count(NormalizedEntity.id))
            .filter(NormalizedEntity.entity_type == "application")
            .group_by(NormalizedEntity.platform)
            .all()
        )
        if user_counts:
            users_str = ", ".join(f"{plat}: {cnt}" for plat, cnt in user_counts)
            ctx_lines.append(f"Users per platform: {users_str}")
        if app_counts:
            apps_str = ", ".join(f"{plat}: {cnt}" for plat, cnt in app_counts)
            ctx_lines.append(f"Third-party apps per platform: {apps_str}")
    except Exception as exc:
        log.warning("ask: could not fetch identity counts: %s", exc)

    # ── Compliance scores ────────────────────────────────────────────────────────
    try:
        overview = _build_control_report(db)
        ctx_lines.append(f"Overall compliance score: {overview.overall_score}%")
        for std in overview.standards:
            if std.total_controls > 0:
                failing_names = [c.name for c in std.controls if c.status == "fail"][:3]
                ctx_lines.append(
                    f"  {std.name}: {std.score}% | {std.passing_controls} pass, "
                    f"{std.failing_controls} fail, {std.not_applicable_controls} N/A"
                    + (f" | Top failures: {', '.join(failing_names)}" if failing_names else "")
                )
    except Exception as exc:
        log.warning("ask: could not build compliance context: %s", exc)

    if req.platform and req.framework:
        try:
            engine = ComplianceEngine()
            result = engine.calculate_score(req.platform, req.framework, db)
            ctx_lines.append(
                f"Focused context — {req.framework} on {req.platform}: {result['score']}% "
                f"({result['passed_rules']}/{result['total_rules']} passing, {result['failed_rules']} failing)"
            )
        except Exception:
            pass

    ctx = "\n".join(ctx_lines) or "No workspace data available yet."
    prompt = (
        f"You are SSPMer, an expert AI security advisor embedded in a SaaS Security Posture Management platform. "
        f"You have full visibility into the organisation's entire workspace: connected platforms, open findings, "
        f"identity counts, and compliance posture across all frameworks.\n\n"
        f"Current workspace data:\n{ctx}\n\n"
        f"User question: {req.question}\n\n"
        f"Answer concisely (2-4 sentences), professionally, using the real data above where relevant:"
    )

    try:
        from core.llm_ollama import _generate
        answer = await asyncio.wait_for(_generate(prompt), timeout=28.0)
        return AskResponse(answer=answer, source="ollama")
    except (Exception, asyncio.TimeoutError) as exc:
        log.warning("AI ask failed: %s", exc)
        answer = _context_aware_fallback(req.question, ctx_lines)
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


# ── PDF builder (pure Python, zero external dependencies) ────────────────────

def _pdf_esc(s: str) -> str:
    """Escape a string for use inside PDF parenthesised literal strings."""
    return (
        s.replace("\\", "\\\\")
         .replace("(", "\\(")
         .replace(")", "\\)")
         .replace("\r", " ")
         .replace("\n", " ")
    )


_SEV_COLORS = {
    "critical": (0.94, 0.27, 0.27),
    "high":     (0.92, 0.55, 0.03),
    "medium":   (0.85, 0.65, 0.03),
    "low":      (0.13, 0.77, 0.37),
}

# Heatmap gradient: (light_rgb, dark_rgb) per severity — count=1 → light, count≥3 → dark
_HEATMAP_GRADIENT = {
    "critical": ((0.99, 0.82, 0.82), (0.82, 0.10, 0.10)),
    "high":     ((0.99, 0.90, 0.72), (0.80, 0.40, 0.00)),
    "medium":   ((0.99, 0.97, 0.72), (0.75, 0.57, 0.00)),
    "low":      ((0.78, 0.95, 0.80), (0.08, 0.60, 0.25)),
}

_UNICODE_REPLACE = str.maketrans({
    '→': '->',   # →
    '←': '<-',   # ←
    '⇒': '=>',   # ⇒
    '—': '--',   # em dash —
    '–': '-',    # en dash –
    '’': "'",    # right single quote
    '‘': "'",    # left single quote
    '“': '"',    # left double quote
    '”': '"',    # right double quote
    '•': '-',    # bullet •
    '…': '...',  # ellipsis …
    ' ': ' ',    # non-breaking space
})


def _ascii_safe(s: str) -> str:
    return s.translate(_UNICODE_REPLACE)


def _heatmap_cell(sev: str, count: int) -> tuple[tuple[float, float, float] | None, str, bool]:
    """Returns (bg_color | None, display_text, use_white_text)."""
    if count == 0:
        return None, '-', False
    grad = _HEATMAP_GRADIENT.get(sev, ((0.9, 0.9, 0.9), (0.5, 0.5, 0.5)))
    t = min((count - 1) / 2.0, 1.0)
    r = grad[0][0] + t * (grad[1][0] - grad[0][0])
    g = grad[0][1] + t * (grad[1][1] - grad[0][1])
    b = grad[0][2] + t * (grad[1][2] - grad[0][2])
    use_white = (sev in ("critical", "high") and count >= 2) or (sev == "low" and count >= 2)
    return (r, g, b), str(count), use_white


def _professional_narrative(fw_name: str, platform: str, score: int, passed: int, total: int,
                             failed: int, failing_rules: list[dict]) -> str:
    posture = "strong" if score >= 75 else "moderate" if score >= 50 else "below threshold"
    audit = "well-positioned for an external audit" if score >= 75 else \
            "partially audit-ready" if score >= 50 else "not yet audit-ready"
    critical = [r for r in failing_rules if r.get("severity", "").lower() == "critical"]
    risk_note = ""
    if critical:
        risk_note = (
            f" Critical exposures include {critical[0]['name']}"
            + (f" and {len(critical) - 1} other critical control(s)" if len(critical) > 1 else "")
            + ", requiring immediate attention."
        )
    return (
        f"The {fw_name} compliance posture for {platform} is {posture}, with {passed} of {total} "
        f"controls passing ({score}%). The organisation is {audit} against this framework's requirements."
        f"{risk_note}\n\n"
        f"The {failed} failing control(s) identified below represent the primary GRC risk exposure. "
        f"Prioritising critical and high-severity findings will yield the greatest improvement in audit "
        f"readiness and regulatory alignment. A structured remediation plan with clear ownership and "
        f"defined timelines is recommended."
    )


_GRC_CONTEXT = {
    "CIS":      "CIS Benchmarks provide prescriptive hardening guidance used as a baseline in SOC 2, ISO 27001, and FedRAMP audits.",
    "SOC2":     "SOC 2 Type II attestation demonstrates to customers and auditors that trust services criteria are continuously met.",
    "ISO27001": "ISO/IEC 27001:2022 certification signals a mature ISMS and is required by many enterprise procurement processes.",
    "NIST-CSF": "NIST CSF v1.1 is widely adopted for US regulatory alignment (HIPAA, FISMA) and supply-chain risk management.",
}


def _build_pdf(report: DbReport, failing_rules: list[dict] | None = None) -> bytes:
    """
    Generate a PDF/1.4 compliance report using only the Python standard library.
    Sections: header, score band, executive summary, GRC context, heatmap, remediation, footer.
    All text is sanitised to ASCII before encoding to avoid '?' replacement glyphs.
    """
    import textwrap

    fw_name = FRAMEWORKS.get(report.framework, {}).get("name", report.framework)
    created = report.created_at.strftime("%Y-%m-%d %H:%M UTC")
    failing_rules = failing_rules or []

    def e(s: str) -> str:
        return _pdf_esc(_ascii_safe(str(s)))

    def rgb(r: float, g: float, b: float) -> str:
        return f"{r:.3f} {g:.3f} {b:.3f}"

    def t(x: int | float, y: int | float, size: float, text: str, bold: bool = False) -> str:
        font = "/Fb" if bold else "/F1"
        return f"BT {font} {size} Tf 1 0 0 1 {int(x)} {int(y)} Tm ({e(text)}) Tj ET"

    def divider(ypos: float) -> str:
        return f"{rgb(0.82, 0.82, 0.82)} RG  0.4 w  20 {int(ypos)} m 592 {int(ypos)} l S"

    def section(ypos: float, label: str) -> list[str]:
        return [
            f"{rgb(0.09, 0.11, 0.17)} rg",
            t(20, ypos, 10.5, label, bold=True),
        ]

    ops: list[str] = []

    # ── Header band ───────────────────────────────────────────────────────────
    ops.append(f"{rgb(0.09, 0.11, 0.17)} rg  0 750 612 42 re f")
    # Accent stripe
    ops.append(f"{rgb(0.25, 0.48, 0.98)} rg  0 748 612 3 re f")
    ops.append(f"{rgb(1,1,1)} rg")
    ops.append(t(20, 768, 14, "SSPM Compliance Report", bold=True))
    ops.append(t(20, 754, 8.5, f"{fw_name}   |   Platform: {report.platform}   |   {created}"))

    # ── Score band ────────────────────────────────────────────────────────────
    if report.score >= 75:
        sc = (0.08, 0.65, 0.28)
    elif report.score >= 50:
        sc = (0.78, 0.52, 0.02)
    else:
        sc = (0.82, 0.14, 0.14)

    # Score block background
    ops.append(f"{rgb(0.97, 0.97, 0.98)} rg  0 688 612 52 re f")
    ops.append(f"{rgb(*sc)} rg")
    ops.append(t(22, 700, 38, f"{report.score}%", bold=True))

    ops.append(f"{rgb(0.3, 0.3, 0.3)} rg")
    ops.append(t(145, 720, 9, f"Framework:    {fw_name}"))
    ops.append(t(145, 707, 9, f"Total Rules:  {report.total_rules}"))
    ops.append(t(145, 694, 9, f"Passing:      {report.passed_rules}   |   Failing: {report.failed_rules}"))

    # Status badge
    badge_label = "COMPLIANT" if report.score >= 75 else "NEEDS WORK" if report.score >= 50 else "AT RISK"
    ops.append(f"{rgb(*sc)} rg  460 696 110 20 re f")
    ops.append(f"{rgb(1,1,1)} rg")
    ops.append(t(483, 703, 9, badge_label, bold=True))

    ops.append(divider(686))
    y = 672.0

    # ── Executive summary ─────────────────────────────────────────────────────
    if report.ai_narrative:
        ops.extend(section(y, "Executive Summary"))
        y -= 16
        ops.append(f"{rgb(0.18, 0.18, 0.18)} rg")
        for para in report.ai_narrative.split("\n"):
            if not para.strip():
                y -= 4
                continue
            for wline in textwrap.wrap(_ascii_safe(para.strip()), width=96):
                if y < 58:
                    break
                ops.append(t(20, y, 9.5, wline))
                y -= 13
            y -= 3
        ops.append(divider(y - 4))
        y -= 16

    # ── GRC context ───────────────────────────────────────────────────────────
    grc_line = _GRC_CONTEXT.get(report.framework, "")
    if grc_line and y > 110:
        ops.extend(section(y, "GRC Context"))
        y -= 14
        ops.append(f"{rgb(0.3, 0.3, 0.3)} rg")
        for wline in textwrap.wrap(_ascii_safe(grc_line), width=96):
            if y < 58:
                break
            ops.append(t(20, y, 9, wline))
            y -= 12
        ops.append(divider(y - 4))
        y -= 16

    # ── Security heatmap ──────────────────────────────────────────────────────
    if failing_rules and y > 130:
        heatmap: dict[str, dict[str, int]] = {}
        for rule in failing_rules:
            cat = _ascii_safe(rule.get("category", "General"))[:26]
            sev = rule.get("severity", "medium").lower()
            heatmap.setdefault(cat, {}).setdefault(sev, 0)
            heatmap[cat][sev] += rule.get("open_count", 1)

        ops.extend(section(y, "Security Heatmap"))
        y -= 15

        sev_cols = ["critical", "high", "medium", "low"]
        col_x   = [230.0, 315.0, 395.0, 470.0]
        col_w   = 70.0
        row_h   = 14.0

        # Header row background
        ops.append(f"{rgb(0.13, 0.15, 0.22)} rg  18 {y - 3} 576 {row_h} re f")
        ops.append(f"{rgb(1,1,1)} rg")
        ops.append(t(20, y + 1, 8, "Category", bold=True))
        for cx, sev in zip(col_x, sev_cols):
            ops.append(t(cx + 4, y + 1, 8, sev.capitalize(), bold=True))
        y -= row_h

        for row_idx, (cat, counts) in enumerate(list(heatmap.items())[:6]):
            if y < 68:
                break
            # Alternating row background
            if row_idx % 2 == 0:
                ops.append(f"{rgb(0.95, 0.95, 0.97)} rg  18 {y - 3} 576 {row_h} re f")
            ops.append(f"{rgb(0.15, 0.15, 0.15)} rg")
            ops.append(t(20, y + 1, 8.5, cat))

            for cx, sev in zip(col_x, sev_cols):
                count = counts.get(sev, 0)
                bg_color, display, use_white = _heatmap_cell(sev, count)
                if bg_color:
                    cr, cg, cb = bg_color
                    ops.append(f"{rgb(cr, cg, cb)} rg  {cx} {y - 2} {col_w - 4} {row_h - 1} re f")
                    ops.append(f"{rgb(1,1,1) if use_white else rgb(0.15, 0.15, 0.15)} rg")
                    ops.append(t(cx + col_w / 2 - 4, y + 1, 8.5, display, bold=True))
                else:
                    ops.append(f"{rgb(0.65, 0.65, 0.65)} rg")
                    ops.append(t(cx + col_w / 2 - 2, y + 1, 8, display))
                ops.append(f"{rgb(0.15, 0.15, 0.15)} rg")
            y -= row_h

        # Table border
        ops.append(
            f"{rgb(0.75, 0.75, 0.80)} RG  0.4 w  "
            f"18 {y - 1} m 594 {y - 1} l S"
        )
        ops.append(divider(y - 3))
        y -= 16

    # ── Remediation actions ───────────────────────────────────────────────────
    if failing_rules and y > 100:
        ops.extend(section(y, "Top Remediation Actions"))
        y -= 16

        for i, rule in enumerate(failing_rules[:4], 1):
            if y < 58:
                break
            sev = rule.get("severity", "medium").lower()
            sr2, sg2, sb2 = _SEV_COLORS.get(sev, (0.5, 0.5, 0.5))

            # Severity pill
            ops.append(f"{rgb(sr2, sg2, sb2)} rg  18 {y - 3} 52 13 re f")
            ops.append(f"{rgb(1,1,1)} rg")
            ops.append(t(20, y + 1, 7, sev.upper(), bold=True))

            ops.append(f"{rgb(0.10, 0.10, 0.10)} rg")
            name = _ascii_safe(rule.get("name", ""))[:90]
            ops.append(t(76, y + 1, 9, f"{i}. {name}", bold=True))
            y -= 14

            remediation = _ascii_safe(rule.get("remediation", "")).strip()
            if remediation and y > 60:
                ops.append(f"{rgb(0.35, 0.35, 0.35)} rg")
                for wline in textwrap.wrap(f"   -> {remediation}", width=94)[:2]:
                    if y < 58:
                        break
                    ops.append(t(20, y, 8.5, wline))
                    y -= 12
            y -= 5

    # ── Footer ────────────────────────────────────────────────────────────────
    ops.append(f"{rgb(0.13, 0.15, 0.22)} rg  0 0 612 28 re f")
    ops.append(f"{rgb(0.6, 0.6, 0.6)} rg")
    ops.append(t(20, 10, 7.5, f"Generated by SSPM Platform   |   {fw_name}   |   {report.platform}   |   Report #{report.id}"))

    # ── Assemble PDF objects ──────────────────────────────────────────────────
    stream = "\n".join(ops).encode("latin-1", errors="replace")

    def obj(n: int, hdr: str, data: bytes | None = None) -> bytes:
        if data is not None:
            return f"{n} 0 obj\n{hdr}\nstream\n".encode() + data + b"\nendstream\nendobj\n"
        return f"{n} 0 obj\n{hdr}\nendobj\n".encode()

    o1 = obj(1, "<< /Type /Catalog /Pages 2 0 R >>")
    o2 = obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    o3 = obj(3, (
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R /Fb 6 0 R >> >> >>"
    ))
    o4 = obj(4, f"<< /Length {len(stream)} >>", stream)
    o5 = obj(5, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    o6 = obj(6, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    chunks = [o1, o2, o3, o4, o5, o6]
    offsets: list[int] = []
    pos = len(header)
    for chunk in chunks:
        offsets.append(pos)
        pos += len(chunk)

    body = header + b"".join(chunks)
    xref_pos = len(body)

    xref = b"xref\n0 7\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()

    trailer = (
        f"trailer\n<< /Size 7 /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()

    return body + xref + trailer


# ── Context-aware fallback (uses real DB data when Ollama is offline) ────────

def _context_aware_fallback(question: str, ctx_lines: list[str]) -> str:
    """
    When Ollama is unavailable, answer using the compliance context that was
    already fetched from the DB, so score/posture questions return real numbers.
    """
    q = question.lower()

    score_keywords = {"score", "posture", "percentage", "percent", "how am i", "how are we",
                      "standing", "overall", "compliance level", "status", "tell me"}
    fw_map = {
        "cis": "CIS Benchmark", "soc2": "SOC 2", "soc 2": "SOC 2",
        "iso27001": "ISO/IEC 27001", "iso 27001": "ISO/IEC 27001", "nist": "NIST",
    }

    if ctx_lines and any(kw in q for kw in score_keywords):
        # Try to match a specific framework first
        for kw, fw_label in fw_map.items():
            if kw in q:
                matching = [l.strip() for l in ctx_lines if fw_label in l]
                if matching:
                    return f"Your {fw_label} compliance posture:\n\n" + "\n".join(matching)

        # Return full posture summary
        lines = [l.strip() for l in ctx_lines if l.strip()]
        if lines:
            return "Here is your current compliance posture:\n\n" + "\n".join(lines)

    # Framework-specific questions without explicit score ask
    if ctx_lines:
        for kw, fw_label in fw_map.items():
            if kw in q:
                matching = [l.strip() for l in ctx_lines if fw_label in l]
                if matching:
                    return f"{fw_label} status: " + " | ".join(matching)

    return _static_compliance_answer(question)


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
