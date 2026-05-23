"""
core/compliance_engine.py — Derives compliance scores from rules + findings,
and persists snapshots after each connector sync.

Usage:
    engine = ComplianceEngine()
    score = engine.calculate_score("github", "CIS", db)
    engine.snapshot_all(db)   # called at end of every sync
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from database.models import ComplianceSnapshot, Finding, Rule

log = logging.getLogger(__name__)

FRAMEWORKS: dict[str, dict[str, str]] = {
    "CIS": {"name": "CIS Benchmark", "prefix": "CIS"},
    "SOC2": {"name": "SOC 2 Type II", "prefix": "SOC2"},
    "ISO27001": {"name": "ISO/IEC 27001:2022", "prefix": "ISO27001"},
    "NIST-CSF": {"name": "NIST Cybersecurity Framework", "prefix": "NIST-CSF"},
}


def _parse_mappings(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    result: list[str] = []
    for m in raw:
        if isinstance(m, str):
            result.append(m)
        elif isinstance(m, dict):
            # YAML dict-style: {'SOC2-TSC': 'CC6.1'} -> 'SOC2-TSC:CC6.1'
            for k, v in m.items():
                result.append(f"{k}:{v}")
    return result


class ComplianceEngine:
    def calculate_score(self, platform: str, framework: str, db: Session) -> dict[str, Any]:
        meta = FRAMEWORKS.get(framework)
        if not meta:
            return _empty(platform, framework)

        rules = db.query(Rule).filter(
            Rule.platform.in_([platform, "cross-platform"]),
            Rule.is_active.is_(True),
        ).all()

        if framework == "CIS":
            # CIS rules are identified by their ID prefix, not compliance_mapping
            mapped = [r for r in rules if r.id.startswith("CIS-")]
        else:
            prefix = meta["prefix"]
            mapped = [r for r in rules if any(m.startswith(prefix) for m in _parse_mappings(r.compliance_mapping))]

        total = len(mapped)
        if total == 0:
            return _empty(platform, framework)

        # The findings table only stores violations.
        # total_count==0 on a scanned platform → no violations → rule passes.
        platform_scanned = (
            db.query(Finding).filter(Finding.platform == platform).limit(1).count() > 0
        )

        passed = 0
        failed = 0
        for rule in mapped:
            total_count = (
                db.query(Finding)
                .filter(Finding.rule_id == rule.id, Finding.platform == platform)
                .count()
            )
            if total_count == 0:
                if platform_scanned:
                    passed += 1   # scanned but no violations → compliant
                continue
            open_count = (
                db.query(Finding)
                .filter(Finding.rule_id == rule.id, Finding.platform == platform, Finding.status == "open")
                .count()
            )
            if open_count == 0:
                passed += 1
            else:
                failed += 1

        covered = passed + failed
        score = round((passed / covered) * 100) if covered > 0 else 100
        return {
            "platform": platform,
            "framework": framework,
            "framework_name": meta["name"],
            "score": score,
            "total_rules": total,
            "passed_rules": passed,
            "failed_rules": failed,
        }

    def snapshot_all(self, db: Session, scan_run_id: str | None = None) -> None:
        """Persist a ComplianceSnapshot for every connected platform × framework."""
        try:
            from database.models import Connector
            connector_platforms = {
                row[0]
                for row in db.query(distinct(Connector.platform_name))
                .filter(Connector.connection_ok.is_(True))
                .all()
            }
            platforms = list(connector_platforms)
        except Exception as exc:
            log.warning("compliance_snapshot: failed to fetch platforms: %s", exc)
            return

        now = datetime.now(timezone.utc)
        added = 0
        for platform in platforms:
            for framework in FRAMEWORKS:
                try:
                    result = self.calculate_score(platform, framework, db)
                    if result["total_rules"] == 0:
                        continue
                    db.add(ComplianceSnapshot(
                        platform=platform,
                        framework=framework,
                        score=result["score"],
                        total_rules=result["total_rules"],
                        passed_rules=result["passed_rules"],
                        failed_rules=result["failed_rules"],
                        snapshot_date=now,
                        scan_run_id=scan_run_id,
                    ))
                    added += 1
                except Exception as exc:
                    log.warning("compliance_snapshot failed platform=%s framework=%s: %s", platform, framework, exc)

        if added:
            try:
                db.commit()
                log.info("compliance_snapshot: saved %d snapshots", added)
            except Exception as exc:
                log.warning("compliance_snapshot: commit failed: %s", exc)
                db.rollback()


def _empty(platform: str, framework: str) -> dict[str, Any]:
    return {
        "platform": platform,
        "framework": framework,
        "framework_name": FRAMEWORKS.get(framework, {}).get("name", framework),
        "score": 0,
        "total_rules": 0,
        "passed_rules": 0,
        "failed_rules": 0,
    }


# ── Score colour ──────────────────────────────────────────────────────────────

def _score_status(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 60:
        return "amber"
    return "red"


# ── Heatmap matrix ────────────────────────────────────────────────────────────

def build_heatmap_matrix(db: Session) -> dict[str, Any]:
    """
    Build a framework × platform compliance score matrix.

    Returns:
        {
          "frameworks": ["CIS", "SOC2", ...],
          "platforms":  ["github", "jira", ...],
          "matrix": {
            "github": {"CIS": {"score": 82, "status": "green"}, ...},
            ...
          }
        }
    """
    engine = ComplianceEngine()
    try:
        from database.models import Connector
        platforms = [
            row[0] for row in db.query(distinct(Connector.platform_name))
            .filter(Connector.connection_ok.is_(True)).all()
        ]
    except Exception as exc:
        log.warning("build_heatmap_matrix: could not fetch platforms: %s", exc)
        return {"frameworks": list(FRAMEWORKS.keys()), "platforms": [], "matrix": {}}

    matrix: dict[str, dict[str, dict]] = {}
    for plat in platforms:
        matrix[plat] = {}
        for fw in FRAMEWORKS:
            result = engine.calculate_score(plat, fw, db)
            if result["total_rules"] > 0:
                matrix[plat][fw] = {
                    "score": result["score"],
                    "status": _score_status(result["score"]),
                    "passed_rules": result["passed_rules"],
                    "failed_rules": result["failed_rules"],
                    "total_rules": result["total_rules"],
                }
            else:
                matrix[plat][fw] = {"score": None, "status": "gray"}

    return {"frameworks": list(FRAMEWORKS.keys()), "platforms": platforms, "matrix": matrix}


# ── Full GRC report structure ─────────────────────────────────────────────────

def build_grc_report_structure(
    db: Session,
    selected_platforms: list[str] | None = None,
    selected_frameworks: list[str] | None = None,
    report_title: str = "SSPM Security Posture Report",
    organisation_name: str = "Your Organisation",
    report_period_days: int = 30,
    classification: str = "Confidential",
) -> dict[str, Any]:
    """
    Build the full GRC report data dictionary used to render templates.
    If selected_platforms or selected_frameworks are None, all connected
    platforms / all frameworks are included.
    """
    engine = ComplianceEngine()

    try:
        from database.models import Connector
        connected = [
            row[0] for row in db.query(distinct(Connector.platform_name))
            .filter(Connector.connection_ok.is_(True)).all()
        ]
    except Exception as exc:
        log.warning("build_grc_report_structure: %s", exc)
        connected = []

    platforms = selected_platforms or connected
    frameworks = selected_frameworks or list(FRAMEWORKS.keys())

    # Per-platform × framework scores
    scores: dict[str, dict[str, dict]] = {}
    for plat in platforms:
        scores[plat] = {}
        for fw in frameworks:
            r = engine.calculate_score(plat, fw, db)
            scores[plat][fw] = r

    # Aggregate overall score across all included scores
    all_passed = sum(
        scores[p][f]["passed_rules"]
        for p in platforms for f in frameworks
        if scores[p][f]["total_rules"] > 0
    )
    all_failed = sum(
        scores[p][f]["failed_rules"]
        for p in platforms for f in frameworks
        if scores[p][f]["total_rules"] > 0
    )
    covered = all_passed + all_failed
    overall_score = round((all_passed / covered) * 100) if covered > 0 else 100

    # Failing rules per framework
    from api.routes.compliance import _collect_failing_rules  # type: ignore[import]
    failing_by_framework: dict[str, list[dict]] = {}
    for fw in frameworks:
        failing_by_framework[fw] = _collect_failing_rules(platforms, fw, db)

    # Trend snapshots (last 30 days)
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        snapshots = (
            db.query(ComplianceSnapshot)
            .filter(ComplianceSnapshot.snapshot_date >= cutoff)
            .order_by(ComplianceSnapshot.snapshot_date)
            .all()
        )
        trend_data = [
            {
                "date": s.snapshot_date.strftime("%Y-%m-%d"),
                "platform": s.platform,
                "framework": s.framework,
                "score": s.score,
            }
            for s in snapshots
        ]
    except Exception as exc:
        log.warning("build_grc_report_structure trends: %s", exc)
        trend_data = []

    heatmap = build_heatmap_matrix(db)

    # ── AI-generated content ──────────────────────────────────────────────────
    ai_executive_summary = ""
    ai_roadmap_intro = ""
    ai_trend_narrative = ""
    enriched_findings: list[dict] = []

    try:
        from core.llm_router import LLMRouter
        router = LLMRouter()

        # Collect all failing rules for enrichment (top 20 by severity)
        all_failing: list[dict] = []
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for fw in frameworks:
            for rule in failing_by_framework.get(fw, []):
                all_failing.append(rule)
        seen = set()
        unique_failing: list[dict] = []
        for r in sorted(all_failing, key=lambda x: sev_order.get(x.get("severity", "low"), 9)):
            key = (r.get("name", ""), r.get("platform", ""))
            if key not in seen:
                seen.add(key)
                unique_failing.append(r)

        # Executive summary (DeepSeek — anonymised scores only)
        fw_scores = {
            fw: round(
                sum(scores[p][fw]["passed_rules"] for p in platforms if scores[p][fw]["total_rules"] > 0) /
                max(sum(scores[p][fw]["passed_rules"] + scores[p][fw]["failed_rules"]
                        for p in platforms if scores[p][fw]["total_rules"] > 0), 1) * 100
            )
            for fw in frameworks
        }
        stats_for_ai = {
            "critical": sum(1 for r in unique_failing if r.get("severity") == "critical"),
            "high": sum(1 for r in unique_failing if r.get("severity") == "high"),
            "medium": sum(1 for r in unique_failing if r.get("severity") == "medium"),
            "top_categories": list({r.get("category", "General") for r in unique_failing[:6]}),
            "overall_score": overall_score,
        }
        ai_executive_summary = router.generate_executive_summary(fw_scores, stats_for_ai)

        # Roadmap intro (DeepSeek — anonymised)
        ai_roadmap_intro = router.generate(
            "roadmap_intro",
            {"total_failing": len(unique_failing), "critical_count": stats_for_ai["critical"],
             "high_count": stats_for_ai["high"]},
        )

        # Trend narrative (DeepSeek — anonymised scores)
        if trend_data:
            trend_summary = {}
            for td in trend_data:
                plat = td["platform"]
                if plat not in trend_summary:
                    trend_summary[plat] = []
                trend_summary[plat].append(td["score"])
            ai_trend_narrative = router.generate_trend_narrative(trend_summary)

        # Per-finding enrichment (top 10 critical/high)
        top_findings = [r for r in unique_failing if r.get("severity") in ("critical", "high")][:10]
        for finding in top_findings:
            enriched = dict(finding)
            enriched["ai_remediation"] = router.generate_remediation(finding)
            enriched["ai_impact"] = router.generate_impact_analysis(finding)
            enriched["exploitation_scenario"] = router.generate_exploitation_scenario(
                finding.get("severity", "high"),
                finding.get("category", "General"),
                finding.get("name", "Unknown control"),
            )
            enriched["ai_source"] = "ollama+deepseek"
            enriched_findings.append(enriched)

    except Exception as exc:
        log.warning("build_grc_report_structure AI enrichment failed: %s", exc)

    return {
        "title": report_title,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "overall_score": overall_score,
        "overall_status": _score_status(overall_score),
        "platforms": platforms,
        "frameworks": frameworks,
        "framework_names": {k: v["name"] for k, v in FRAMEWORKS.items()},
        "scores": scores,
        "heatmap": heatmap,
        "failing_by_framework": failing_by_framework,
        "trend_data": trend_data,
        "passed_rules": all_passed,
        "failed_rules": all_failed,
        "total_rules": covered,
        "organisation_name": organisation_name,
        "report_period_days": report_period_days,
        "classification": classification,
        "ai_executive_summary": ai_executive_summary,
        "ai_roadmap_intro": ai_roadmap_intro,
        "ai_trend_narrative": ai_trend_narrative,
        "enriched_findings": enriched_findings,
    }


# ── HTML → PDF via weasyprint + Jinja2 ───────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).parent / "templates" / "report"


def generate_pdf_report(report_data: dict[str, Any], output_path: str | None = None) -> bytes:
    """
    Render the GRC report as a PDF using Jinja2 templates + weasyprint.
    Falls back gracefully to a minimal PDF if weasyprint is not installed.

    Args:
        report_data: dict returned by build_grc_report_structure()
        output_path: optional file path to write the PDF

    Returns:
        PDF bytes
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        from weasyprint import HTML as WeasyHTML

        env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
        template = env.get_template("base.html")
        html_content = template.render(**report_data)

        pdf_bytes: bytes = WeasyHTML(string=html_content, base_url=str(_TEMPLATE_DIR)).write_pdf()
    except ImportError:
        log.warning("weasyprint/jinja2 not installed — using fallback PDF builder")
        pdf_bytes = _fallback_pdf(report_data)
    except Exception as exc:
        log.warning("generate_pdf_report failed: %s — using fallback", exc)
        pdf_bytes = _fallback_pdf(report_data)

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as fh:
            fh.write(pdf_bytes)

    return pdf_bytes


def _fallback_pdf(report_data: dict[str, Any]) -> bytes:
    """Minimal single-page PDF when weasyprint is unavailable."""
    title = str(report_data.get("title", "SSPM Report"))
    score = report_data.get("overall_score", 0)
    generated_at = str(report_data.get("generated_at", ""))
    platforms = ", ".join(report_data.get("platforms", []))

    def e(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\n", " ")

    if score >= 75:
        sc_rgb = "0.08 0.65 0.28"
    elif score >= 50:
        sc_rgb = "0.78 0.52 0.02"
    else:
        sc_rgb = "0.82 0.14 0.14"

    ops = [
        "0.09 0.11 0.17 rg  0 750 612 42 re f",
        "0.25 0.48 0.98 rg  0 748 612 3 re f",
        "1 1 1 rg",
        f"BT /Fb 13 Tf 1 0 0 1 20 768 Tm ({e(title)}) Tj ET",
        f"BT /F1 8.5 Tf 1 0 0 1 20 754 Tm ({e(generated_at)}) Tj ET",
        "0.97 0.97 0.98 rg  0 688 612 52 re f",
        f"{sc_rgb} rg",
        f"BT /Fb 38 Tf 1 0 0 1 22 700 Tm ({score}%) Tj ET",
        "0.3 0.3 0.3 rg",
        f"BT /F1 9 Tf 1 0 0 1 145 707 Tm (Platforms: {e(platforms)}) Tj ET",
    ]
    stream = "\n".join(ops).encode("latin-1", errors="replace")

    def obj(n: int, hdr: str, data: bytes | None = None) -> bytes:
        if data is not None:
            return f"{n} 0 obj\n{hdr}\nstream\n".encode() + data + b"\nendstream\nendobj\n"
        return f"{n} 0 obj\n{hdr}\nendobj\n".encode()

    o1 = obj(1, "<< /Type /Catalog /Pages 2 0 R >>")
    o2 = obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    o3 = obj(3, "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R /Fb 6 0 R >> >> >>")
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
