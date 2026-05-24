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
    scan_run_id: str | None = None


class GenerateReportRequest(BaseModel):
    title: str = "SSPM Compliance Report"
    platforms: list[str] | None = None        # None = all connected
    frameworks: list[str] | None = None       # None = all frameworks
    include_ai_narrative: bool = True
    include_exploitation_scenarios: bool = True
    include_impact_analysis: bool = True
    ai_provider_executive: str = "deepseek"
    ai_provider_remediation: str = "ollama"
    report_period_days: int = 30
    classification: str = "Confidential"
    output_format: str = "pdf"
    organisation_name: str = "Your Organisation"
    # Legacy compat
    platform: str = "all"
    framework: str = "SOC2"
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
    status: str = "complete"
    report_title: str | None = None
    platforms_assessed: list[str] | None = None
    frameworks_assessed: list[str] | None = None


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
        connector_platforms = {
            row[0]
            for row in db.query(distinct(Connector.platform_name))
            .filter(Connector.connection_ok.is_(True))
            .all()
        }
        platforms = list(connector_platforms)
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
            scan_run_id=s.scan_run_id,
        )
        for s in q.order_by(ComplianceSnapshot.snapshot_date).all()
    ]


def _collect_failing_rules(platforms: list[str], framework: str, db: Session) -> list[dict]:
    """Collect open failing rule dicts across one or more platforms for a framework."""
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    results: list[dict] = []
    try:
        for plat in platforms:
            all_rules = db.query(Rule).filter(
                Rule.platform.in_([plat, "cross-platform"]), Rule.is_active.is_(True)
            ).all()
            if framework == "CIS":
                fw_rules = [r for r in all_rules if r.id.startswith("CIS-")]
            else:
                prefix = FRAMEWORKS.get(framework, {}).get("prefix", "")
                fw_rules = [r for r in all_rules if any(m.startswith(prefix) for m in _parse_mappings(r.compliance_mapping))]
            for rule in fw_rules:
                open_count = db.query(Finding).filter(
                    Finding.rule_id == rule.id, Finding.platform == plat, Finding.status == "open"
                ).count()
                if open_count > 0:
                    results.append({
                        "name": rule.name,
                        "severity": rule.severity or "medium",
                        "category": rule.category or "General",
                        "remediation": rule.remediation or "",
                        "open_count": open_count,
                        "platform": plat,
                    })
        results.sort(key=lambda r: sev_order.get(r["severity"].lower(), 99))
    except Exception as exc:
        log.warning("_collect_failing_rules: %s", exc)
    return results


@router.post("/report", response_model=StoredReport, status_code=201)
async def generate_report(req: GenerateReportRequest, db: DB) -> StoredReport:
    """Generate a compliance report. Use platform='all' to aggregate all connected platforms."""
    engine = ComplianceEngine()

    # Resolve platforms — use new-style `platforms` list if provided, else legacy `platform` field
    if req.platforms:
        platforms = req.platforms
    elif req.platform == "all":
        platforms = [
            row[0] for row in db.query(distinct(Connector.platform_name))
            .filter(Connector.connection_ok.is_(True)).all()
        ]
        if not platforms:
            raise HTTPException(status_code=400, detail="No connected platforms found")
    else:
        platforms = [req.platform]

    # Resolve frameworks — use new-style `frameworks` list if provided, else legacy `framework` field
    selected_frameworks = req.frameworks or [req.framework]

    total_rules = passed_rules = failed_rules = 0
    for plat in platforms:
        for fw in selected_frameworks:
            r = engine.calculate_score(plat, fw, db)
            total_rules += r["total_rules"]
            passed_rules += r["passed_rules"]
            failed_rules += r["failed_rules"]
    covered = passed_rules + failed_rules
    agg_score = round((passed_rules / covered) * 100) if covered > 0 else 100
    result = {"score": agg_score, "total_rules": total_rules, "passed_rules": passed_rules, "failed_rules": failed_rules}
    platforms_label = ", ".join(platforms)

    failing_rules_info = _collect_failing_rules(platforms, req.framework, db)

    narrative: str | None = None
    if req.with_ai_narrative or req.include_ai_narrative:
        try:
            from core.llm_ollama import _generate
            fw_name = FRAMEWORKS.get(req.framework, {}).get("name", req.framework)
            failing_ctx = "\n".join(
                f"- [{r.get('platform', platforms_label)}] {r['name']} ({r['severity']}): {r['open_count']} open finding(s)"
                for r in failing_rules_info[:5]
            ) or "None — all controls passing."
            prompt = (
                f"You are a GRC (Governance, Risk, Compliance) expert. Write a concise 3-paragraph executive "
                f"summary for a {fw_name} compliance report.\n\n"
                f"Platforms: {platforms_label} | Score: {result['score']}% | "
                f"Passing: {result['passed_rules']}/{result['total_rules']} rules | "
                f"Failing: {result['failed_rules']}\n\n"
                f"Top failing controls:\n{failing_ctx}\n\n"
                f"Paragraph 1: Current {fw_name} posture and audit readiness across all platforms. "
                f"Paragraph 2: Priority remediation actions and GRC risk impact. "
                f"Paragraph 3: CIA triad analysis — which of Confidentiality, Integrity, or Availability "
                f"is most at risk from the top failing controls, and why in 1-2 sentences. "
                f"Professional tone, under 160 words total, no bullet points."
            )
            narrative = await asyncio.wait_for(_generate(prompt), timeout=28.0)
        except (Exception, asyncio.TimeoutError) as exc:
            log.warning("AI narrative failed: %s", exc)
            fw_name = FRAMEWORKS.get(req.framework, {}).get("name", req.framework)
            narrative = _professional_narrative(
                fw_name, platforms_label, result["score"],
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


@router.get("/heatmap")
def get_heatmap(db: DB) -> dict:
    """Return the framework × platform compliance score matrix."""
    from core.compliance_engine import build_heatmap_matrix
    return build_heatmap_matrix(db)


@router.get("/ai-status")
def get_ai_status() -> dict:
    """Return availability and routing status for Ollama and DeepSeek."""
    from core.llm_router import LLMRouter
    llm_router = LLMRouter()
    return llm_router.check_status()


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, db: DB) -> Response:
    report = db.get(DbReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.pdf_path:
        try:
            import os as _os
            _os.remove(report.pdf_path)
        except OSError:
            pass
    db.delete(report)
    db.commit()
    return Response(status_code=204)


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

    from core.compliance_engine import build_grc_report_structure, generate_pdf_report

    platforms = getattr(report, "platforms_assessed", None) or (
        None if report.platform == "all" else [report.platform]
    )
    frameworks = getattr(report, "frameworks_assessed", None) or [report.framework]
    title = getattr(report, "report_title", None) or f"Compliance Report — {report.framework}"

    report_data = build_grc_report_structure(
        db,
        selected_platforms=platforms,
        selected_frameworks=frameworks,
        report_title=title,
    )
    if report.ai_narrative and not report_data.get("ai_executive_summary"):
        report_data["ai_executive_summary"] = report.ai_narrative

    pdf_bytes = generate_pdf_report(report_data)
    filename = f"compliance_{report.platform}_{report.framework}_{report_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report/full-posture")
def download_full_posture_report(db: DB) -> Response:
    """Download a comprehensive PDF covering all frameworks × all connected platforms."""
    connected_platforms = [
        row[0] for row in db.query(distinct(Connector.platform_name))
        .filter(Connector.connection_ok.is_(True)).all()
    ]
    if not connected_platforms:
        raise HTTPException(status_code=400, detail="No connected platforms found")

    from core.compliance_engine import build_grc_report_structure, generate_pdf_report

    report_data = build_grc_report_structure(
        db,
        selected_platforms=connected_platforms,
        report_title="Full Security Posture Report",
    )
    pdf_bytes = generate_pdf_report(report_data)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="sspm_full_posture_{today}.pdf"'},
    )


@router.post("/ask", response_model=AskResponse)
async def ask_compliance(req: AskRequest, db: DB) -> AskResponse:
    sections: list[str] = []
    ctx_lines: list[str] = []  # kept for _context_aware_fallback

    # ── Section 1: Connected platforms ──────────────────────────────────────────
    connected_names: list[str] = []
    try:
        connectors = db.query(Connector).all()
        connected_names = [c.platform_name for c in connectors if c.connection_ok]
        unhealthy = [c.platform_name for c in connectors if not c.connection_ok]
        plat_line = f"Healthy: {', '.join(connected_names)}" if connected_names else "None connected"
        if unhealthy:
            plat_line += f" | Unhealthy: {', '.join(unhealthy)}"
        sections.append(f"=== CONNECTED PLATFORMS ===\n{plat_line}")
        if connected_names:
            ctx_lines.append(f"Connected platforms (healthy): {', '.join(connected_names)}")
    except Exception as exc:
        log.warning("ask: connectors: %s", exc)

    # ── Section 2: Compliance scores per platform × framework ───────────────────
    try:
        engine = ComplianceEngine()
        score_rows: list[str] = []
        total_pass = total_fail = 0
        for plat in connected_names:
            for fw_key, fw_meta in FRAMEWORKS.items():
                r = engine.calculate_score(plat, fw_key, db)
                if r["total_rules"] > 0:
                    score_rows.append(
                        f"  {plat} / {fw_meta['name']}: {r['score']}%"
                        f" ({r['passed_rules']} pass, {r['failed_rules']} fail"
                        f" out of {r['total_rules']} controls)"
                    )
                    total_pass += r["passed_rules"]
                    total_fail += r["failed_rules"]
                    ctx_lines.append(
                        f"  {fw_meta['name']}: {r['score']}% | {r['passed_rules']} pass,"
                        f" {r['failed_rules']} fail"
                    )
        if score_rows:
            covered = total_pass + total_fail
            overall = round(total_pass / covered * 100) if covered else 0
            ctx_lines.insert(0, f"Overall compliance score: {overall}%")
            sections.append(
                f"=== COMPLIANCE SCORES ===\nOverall: {overall}%\n" + "\n".join(score_rows)
            )
    except Exception as exc:
        log.warning("ask: scores: %s", exc)

    # ── Section 3: ALL failing controls with remediation steps ──────────────────
    try:
        failing_blocks: list[str] = []
        for plat in connected_names:
            for fw_key, fw_meta in FRAMEWORKS.items():
                rules = _collect_failing_rules([plat], fw_key, db)
                if not rules:
                    continue
                block = [f"\n[{plat.upper()} / {fw_meta['name']}]"]
                for r in rules[:20]:
                    rem = (r.get("remediation") or "").strip()
                    line = (
                        f"  • [{r['severity'].upper()}] {r['name']}"
                        f" — {r['open_count']} open finding(s)"
                    )
                    if rem:
                        line += f"\n    → Fix: {rem[:250]}"
                    block.append(line)
                failing_blocks.append("\n".join(block))
                top3 = [r["name"] for r in rules[:3]]
                ctx_lines.append(
                    f"  {fw_meta['name']} top failures: {', '.join(top3)}"
                )
        if failing_blocks:
            sections.append(
                "=== FAILING CONTROLS & REMEDIATION STEPS ===\n"
                + "\n".join(failing_blocks)
            )
        else:
            sections.append("=== FAILING CONTROLS ===\nNone — all assessed controls pass.")
    except Exception as exc:
        log.warning("ask: failing controls: %s", exc)

    # ── Section 4: Open findings summary ────────────────────────────────────────
    try:
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sev_totals = (
            db.query(Finding.severity, func.count(Finding.id))
            .filter(Finding.status == "open")
            .group_by(Finding.severity)
            .all()
        )
        cat_totals = (
            db.query(Finding.category, func.count(Finding.id))
            .filter(Finding.status == "open")
            .group_by(Finding.category)
            .all()
        )
        total_open = sum(cnt for _, cnt in sev_totals)
        sev_str = ", ".join(
            f"{s}: {c}"
            for s, c in sorted(sev_totals, key=lambda x: sev_order.get(x[0] or "low", 99))
        )
        cat_str = ", ".join(
            f"{(cat or 'Uncategorized')}: {cnt}"
            for cat, cnt in sorted(cat_totals, key=lambda x: -x[1])[:8]
        )
        findings_block = f"Total open: {total_open}\nBy severity: {sev_str}"
        if cat_str:
            findings_block += f"\nBy category: {cat_str}"
        sections.append(f"=== OPEN FINDINGS ===\n{findings_block}")
        ctx_lines.append(f"Open findings: {total_open} total ({sev_str})")
    except Exception as exc:
        log.warning("ask: findings summary: %s", exc)

    # ── Section 5: Identities & third-party apps ────────────────────────────────
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
        ident_lines: list[str] = []
        for plat, cnt in user_counts:
            ident_lines.append(f"  {plat}: {cnt} users")
            ctx_lines.append(f"Users on {plat}: {cnt}")
        for plat, cnt in app_counts:
            ident_lines.append(f"  {plat}: {cnt} third-party apps")
        if ident_lines:
            sections.append("=== IDENTITIES & THIRD-PARTY APPS ===\n" + "\n".join(ident_lines))
    except Exception as exc:
        log.warning("ask: identities: %s", exc)

    # ── Section 6: Focused context (when caller passes platform+framework) ───────
    if req.platform and req.framework:
        try:
            engine = ComplianceEngine()
            r = engine.calculate_score(req.platform, req.framework, db)
            focused_rules = _collect_failing_rules([req.platform], req.framework, db)
            focused: list[str] = [
                f"{req.framework} on {req.platform}: {r['score']}%"
                f" ({r['passed_rules']}/{r['total_rules']} controls passing,"
                f" {r['failed_rules']} failing)"
            ]
            if focused_rules:
                focused.append("Failing controls with fixes:")
                for rule in focused_rules:
                    rem = (rule.get("remediation") or "").strip()[:250]
                    focused.append(
                        f"  • [{rule['severity'].upper()}] {rule['name']}"
                        + (f"\n    Fix: {rem}" if rem else "")
                    )
            sections.append("=== FOCUSED CONTEXT ===\n" + "\n".join(focused))
            ctx_lines.append(
                f"Focused — {req.framework} on {req.platform}: {r['score']}%"
                f" ({r['failed_rules']} failing)"
            )
        except Exception:
            pass

    ctx_block = "\n\n".join(sections) or "No workspace data available yet."
    prompt = (
        "You are SSPMer, an expert AI security advisor embedded in a SaaS Security Posture"
        " Management platform. You have FULL visibility into the organisation's real-time"
        " security data provided below.\n"
        "Rules:\n"
        "- Answer using ONLY the data in the workspace block — never invent numbers.\n"
        "- For simple factual questions: answer in 2-3 sentences, citing real values.\n"
        "- For complex questions (gap analysis, remediation plans, framework requirements,"
        " prioritization): give a structured answer with bullet points and section headers.\n"
        "- If the data shows no issues, say so confidently.\n\n"
        f"WORKSPACE DATA:\n{ctx_block}\n\n"
        f"USER QUESTION: {req.question}\n\n"
        "Answer:"
    )

    try:
        from core.llm_ollama import _generate_chat
        answer = await asyncio.wait_for(_generate_chat(prompt), timeout=45.0)
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
    cia_note = (
        "From a CIA triad perspective, Confidentiality and Integrity are the primary risk dimensions "
        "given the access-control and authentication gaps identified. Availability risk is secondary "
        "but should not be overlooked if privileged account controls are not addressed promptly."
    ) if failed > 0 else (
        "All monitored controls are passing. Confidentiality, Integrity, and Availability posture "
        "is currently satisfactory under this framework."
    )
    return (
        f"The {fw_name} compliance posture for {platform} is {posture}, with {passed} of {total} "
        f"controls passing ({score}%). The organisation is {audit} against this framework's requirements."
        f"{risk_note}\n\n"
        f"The {failed} failing control(s) identified below represent the primary GRC risk exposure. "
        f"Prioritising critical and high-severity findings will yield the greatest improvement in audit "
        f"readiness and regulatory alignment. A structured remediation plan with clear ownership and "
        f"defined timelines is recommended.\n\n"
        f"{cia_note}"
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


def _build_full_posture_pdf(
    platforms: list[str],
    platform_scores: dict[str, list[dict]],
    failing_rules: list[dict],
    narrative: str | None = None,
) -> bytes:
    """Comprehensive full-posture PDF: all frameworks × all connected platforms."""
    import textwrap

    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def e(s: str) -> str:
        return _pdf_esc(_ascii_safe(str(s)))

    def rgb(r: float, g: float, b: float) -> str:
        return f"{r:.3f} {g:.3f} {b:.3f}"

    def t(x: float, y: float, size: float, text: str, bold: bool = False) -> str:
        font = "/Fb" if bold else "/F1"
        return f"BT {font} {size} Tf 1 0 0 1 {int(x)} {int(y)} Tm ({e(text)}) Tj ET"

    def divider(ypos: float) -> str:
        return f"{rgb(0.82, 0.82, 0.82)} RG  0.4 w  20 {int(ypos)} m 592 {int(ypos)} l S"

    def section(ypos: float, label: str) -> list[str]:
        return [f"{rgb(0.09, 0.11, 0.17)} rg", t(20, ypos, 10.5, label, bold=True)]

    all_results = [r for scores in platform_scores.values() for r in scores]
    total_passed = sum(r["passed_rules"] for r in all_results)
    total_failed = sum(r["failed_rules"] for r in all_results)
    covered = total_passed + total_failed
    overall_score = round((total_passed / covered) * 100) if covered > 0 else 100

    ops: list[str] = []

    # Header
    ops.append(f"{rgb(0.09, 0.11, 0.17)} rg  0 750 612 42 re f")
    ops.append(f"{rgb(0.25, 0.48, 0.98)} rg  0 748 612 3 re f")
    ops.append(f"{rgb(1,1,1)} rg")
    ops.append(t(20, 768, 13, "SSPM Full Security Posture Report", bold=True))
    ops.append(t(20, 754, 8.5, f"All Platforms: {', '.join(platforms)}   |   {created}"))

    # Score band
    sc = (0.08, 0.65, 0.28) if overall_score >= 75 else (0.78, 0.52, 0.02) if overall_score >= 50 else (0.82, 0.14, 0.14)
    ops.append(f"{rgb(0.97, 0.97, 0.98)} rg  0 688 612 52 re f")
    ops.append(f"{rgb(*sc)} rg")
    ops.append(t(22, 700, 38, f"{overall_score}%", bold=True))
    ops.append(f"{rgb(0.3, 0.3, 0.3)} rg")
    ops.append(t(145, 720, 9, f"Platforms:    {len(platforms)} connected  ({', '.join(platforms)})"))
    ops.append(t(145, 707, 9, f"Total Rules:  {covered}   |   Passing: {total_passed}   |   Failing: {total_failed}"))
    ops.append(t(145, 694, 9, f"Frameworks:   {', '.join(FRAMEWORKS.keys())}"))
    badge_label = "COMPLIANT" if overall_score >= 75 else "NEEDS WORK" if overall_score >= 50 else "AT RISK"
    ops.append(f"{rgb(*sc)} rg  460 696 110 20 re f")
    ops.append(f"{rgb(1,1,1)} rg")
    ops.append(t(483, 703, 9, badge_label, bold=True))
    ops.append(divider(686))
    y = 672.0

    # Executive narrative
    if narrative:
        ops.extend(section(y, "Executive Summary"))
        y -= 16
        ops.append(f"{rgb(0.18, 0.18, 0.18)} rg")
        for para in narrative.split("\n"):
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

    # Platform × Framework matrix
    if y > 160:
        ops.extend(section(y, "Platform x Framework Score Matrix"))
        y -= 16
        fw_list = list(FRAMEWORKS.keys())
        col_w = 88.0
        col_x = [190.0 + i * col_w for i in range(len(fw_list))]
        row_h = 14.0

        ops.append(f"{rgb(0.13, 0.15, 0.22)} rg  18 {y - 3} 576 {row_h} re f")
        ops.append(f"{rgb(1,1,1)} rg")
        ops.append(t(20, y + 1, 8, "Platform", bold=True))
        for cx, fw in zip(col_x, fw_list):
            ops.append(t(cx + 2, y + 1, 7.5, FRAMEWORKS[fw]["name"][:15], bold=True))
        y -= row_h

        for row_idx, plat in enumerate(platforms):
            if y < 68:
                break
            scores_by_fw = {r["framework"]: r["score"] for r in platform_scores.get(plat, [])}
            if row_idx % 2 == 0:
                ops.append(f"{rgb(0.95, 0.95, 0.97)} rg  18 {y - 3} 576 {row_h} re f")
            ops.append(f"{rgb(0.15, 0.15, 0.15)} rg")
            ops.append(t(20, y + 1, 8.5, plat.capitalize()))
            for cx, fw in zip(col_x, fw_list):
                sv = scores_by_fw.get(fw)
                if sv is not None:
                    sc2 = (0.08, 0.65, 0.28) if sv >= 75 else (0.78, 0.52, 0.02) if sv >= 50 else (0.82, 0.14, 0.14)
                    ops.append(f"{rgb(*sc2)} rg")
                    ops.append(t(cx + 2, y + 1, 8.5, f"{sv}%", bold=True))
                else:
                    ops.append(f"{rgb(0.65, 0.65, 0.65)} rg")
                    ops.append(t(cx + 2, y + 1, 8, "N/A"))
                ops.append(f"{rgb(0.15, 0.15, 0.15)} rg")
            y -= row_h

        ops.append(divider(y - 3))
        y -= 16

    # GRC requirements overview
    if y > 120:
        ops.extend(section(y, "GRC Framework Requirements"))
        y -= 14
        for fw, ctx_text in _GRC_CONTEXT.items():
            if y < 68:
                break
            ops.append(f"{rgb(0.09, 0.11, 0.17)} rg")
            ops.append(t(20, y, 8.5, f"{FRAMEWORKS.get(fw, {}).get('name', fw)}:", bold=True))
            y -= 12
            ops.append(f"{rgb(0.35, 0.35, 0.35)} rg")
            for wline in textwrap.wrap(_ascii_safe(ctx_text), width=94)[:2]:
                if y < 68:
                    break
                ops.append(t(20, y, 8, wline))
                y -= 11
            y -= 4
        ops.append(divider(y - 4))
        y -= 16

    # Top failing controls
    if failing_rules and y > 100:
        ops.extend(section(y, "Top Failing Controls (All Platforms & Frameworks)"))
        y -= 16
        for i, rule in enumerate(failing_rules[:5], 1):
            if y < 58:
                break
            sev = rule.get("severity", "medium").lower()
            sr2, sg2, sb2 = _SEV_COLORS.get(sev, (0.5, 0.5, 0.5))
            ops.append(f"{rgb(sr2, sg2, sb2)} rg  18 {y - 3} 52 13 re f")
            ops.append(f"{rgb(1,1,1)} rg")
            ops.append(t(20, y + 1, 7, sev.upper(), bold=True))
            ops.append(f"{rgb(0.10, 0.10, 0.10)} rg")
            plat_tag = f"[{rule.get('platform', '')}] " if rule.get("platform") else ""
            name = _ascii_safe(f"{plat_tag}{rule.get('name', '')}")[:86]
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

    # Footer
    ops.append(f"{rgb(0.13, 0.15, 0.22)} rg  0 0 612 28 re f")
    ops.append(f"{rgb(0.6, 0.6, 0.6)} rg")
    ops.append(t(20, 10, 7.5, f"Generated by SSPM Platform   |   Full Security Posture Report   |   {created}"))

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
    trailer = f"trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
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
        "I don't have a specific answer for that question yet. "
        "For framework guidance, consult: CIS GitHub Benchmark (cisecurity.org), "
        "SOC 2 Trust Services Criteria (aicpa.org), ISO 27001 (iso.org), or NIST CSF (nist.gov). "
        "You can also open individual findings in the Remediation tab for step-by-step fix instructions."
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
        status=getattr(r, "status", "complete"),
        report_title=getattr(r, "report_title", None),
        platforms_assessed=getattr(r, "platforms_assessed", None),
        frameworks_assessed=getattr(r, "frameworks_assessed", None),
    )
