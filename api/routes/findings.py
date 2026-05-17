"""
/findings  –  view and manage detected security findings.

Endpoints:
  GET    /findings/summary                  – counts by severity/status
  GET    /findings/cross-platform           – cross-SaaS correlated findings
  GET    /findings/                         – list with filters
  GET    /findings/{id}                     – single finding with full evidence
  PUT    /findings/{id}/status              – lifecycle transition (justification required)
  POST   /findings/{id}/dismiss             – quick dismiss shortcut
  POST   /findings/{id}/analyze             – run LLM judge on one finding
  POST   /findings/analyze-batch            – run LLM judge on multiple findings
"""
from datetime import datetime, timezone, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database.models import Finding, Rule
from database.schemas import StatusUpdateRequest
from database.session import get_db

router = APIRouter(prefix="/findings", tags=["findings"])

DB = Annotated[Session, Depends(get_db)]

_STATUSES_REQUIRING_JUSTIFICATION = {"false_positive", "accepted_risk"}


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_summary(db: DB) -> dict[str, Any]:
    """Return finding counts grouped by severity and status."""
    by_sev = dict(
        db.query(Finding.severity, func.count(Finding.id))
        .filter(Finding.status == "open")
        .group_by(Finding.severity)
        .all()
    )
    by_status = dict(
        db.query(Finding.status, func.count(Finding.id))
        .group_by(Finding.status)
        .all()
    )
    total = db.query(func.count(Finding.id)).filter(Finding.status == "open").scalar()
    return {
        "total": total,
        "open_by_severity": {
            "critical": by_sev.get("critical", 0),
            "high":     by_sev.get("high", 0),
            "medium":   by_sev.get("medium", 0),
            "low":      by_sev.get("low", 0),
        },
        "by_status": by_status,
    }


# ── Cross-platform ────────────────────────────────────────────────────────────

@router.get("/cross-platform")
def list_cross_platform_findings(
    db: DB,
    limit: Annotated[int, Query(le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    """
    Return findings whose category contains 'cross_platform' or 'cross-platform',
    leveraging FEDERATED_IDENTITY correlations.
    """
    findings = (
        db.query(Finding)
        .filter(
            Finding.status == "open",
            Finding.category.ilike("%cross%platform%"),
        )
        .order_by(Finding.severity, Finding.last_detected.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_finding_to_dict(f, db, include_evidence=True) for f in findings]


# ── List / Get ────────────────────────────────────────────────────────────────

@router.get("/")
def list_findings(
    db: DB,
    severity: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query(description="open|resolved|false_positive|accepted_risk")] = None,
    platform: Annotated[str | None, Query()] = None,
    connector_id: Annotated[str | None, Query()] = None,
    rule_id: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    q = db.query(Finding)
    if severity:
        q = q.filter(Finding.severity == severity)
    # status="all" → no filter; empty/None → default to "open"
    if status and status != "all":
        q = q.filter(Finding.status == status)
    elif not status:
        q = q.filter(Finding.status == "open")
    if platform:
        q = q.filter(Finding.platform == platform)
    if connector_id:
        q = q.filter(Finding.connector_id == connector_id)
    if rule_id:
        q = q.filter(Finding.rule_id == rule_id)
    if category:
        q = q.filter(Finding.category == category)

    findings = q.order_by(Finding.severity, Finding.last_detected.desc()).offset(offset).limit(limit).all()
    return [_finding_to_dict(f, db) for f in findings]


@router.get("/trend")
def get_findings_trend(
    db: DB,
    platform: Annotated[str | None, Query()] = None,
    connector_id: Annotated[str | None, Query()] = None,
    days: Annotated[int, Query(le=365)] = 90,
) -> list[dict[str, Any]]:
    """
    Weekly finding counts grouped by status for the past N days.
    Returns list of { week, open, resolved, false_positive, accepted_risk }.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        db.query(
            func.date_trunc("week", Finding.first_detected).label("week"),
            Finding.status,
            func.count(Finding.id).label("cnt"),
        )
        .filter(Finding.first_detected >= since)
    )
    if platform:
        q = q.filter(Finding.platform == platform)
    if connector_id:
        q = q.filter(Finding.connector_id == connector_id)

    rows = q.group_by(text("week"), Finding.status).order_by(text("week")).all()

    weeks: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.week is None:
            continue
        w = row.week.strftime("%Y-%m-%d")
        if w not in weeks:
            weeks[w] = {"week": w, "open": 0, "resolved": 0, "false_positive": 0, "accepted_risk": 0}
        if row.status in weeks[w]:
            weeks[w][row.status] = row.cnt

    return sorted(weeks.values(), key=lambda x: x["week"])


@router.get("/{finding_id}")
def get_finding(finding_id: int, db: DB) -> dict[str, Any]:
    finding = _get_finding_or_404(finding_id, db)
    return _finding_to_dict(finding, db, include_evidence=True)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@router.put(
    "/{finding_id}/status",
    responses={
        422: {"description": "Invalid status or missing justification"},
        404: {"description": "Finding not found"},
    },
)
def update_status(
    finding_id: int,
    db: DB,
    payload: Annotated[StatusUpdateRequest, Body(...)],
) -> dict[str, Any]:
    """
    Update finding status.

    `justification` is **required** when transitioning to
    `false_positive` or `accepted_risk`.
    """
    _validate_status(payload.status, {"open", "resolved", "false_positive", "accepted_risk"})

    if payload.status in _STATUSES_REQUIRING_JUSTIFICATION and not (payload.justification or "").strip():
        raise HTTPException(
            status_code=422,
            detail=f"justification is required when status is '{payload.status}'",
        )

    finding = _get_finding_or_404(finding_id, db)
    now = datetime.now(timezone.utc)

    finding.status = payload.status
    finding.status_changed_at = now

    if payload.justification:
        finding.justification = payload.justification.strip()

    if payload.status == "resolved":
        finding.resolved_at = now
    elif payload.status == "open":
        finding.resolved_at = None

    db.commit()
    db.refresh(finding)
    return _finding_to_dict(finding, db)


@router.post(
    "/{finding_id}/dismiss",
    responses={
        422: {"description": "Invalid dismiss reason or missing justification"},
        404: {"description": "Finding not found"},
    },
)
def dismiss_finding(
    finding_id: int,
    db: DB,
    reason: Annotated[str, Query(description="false_positive|accepted_risk")],
    justification: Annotated[str, Query(description="Required explanation")] = "",
) -> dict[str, Any]:
    _validate_status(reason, {"false_positive", "accepted_risk"})
    if not justification.strip():
        raise HTTPException(
            status_code=422,
            detail=f"justification is required when dismissing as '{reason}'",
        )
    finding = _get_finding_or_404(finding_id, db)
    now = datetime.now(timezone.utc)
    finding.status = reason
    finding.justification = justification.strip()
    finding.status_changed_at = now
    finding.resolved_at = now
    db.commit()
    db.refresh(finding)
    return _finding_to_dict(finding, db)


# ── LLM Judge ─────────────────────────────────────────────────────────────────

@router.post(
    "/{finding_id}/analyze",
    responses={
        404: {"description": "Finding not found"},
        503: {"description": "LLM judge unavailable"},
    },
)
def analyze_finding(finding_id: int, db: DB) -> dict[str, Any]:
    """
    Run the LLM judge on a single finding.
    Persists severity reassessment, exploitability, and enhanced remediation.
    """
    finding = _get_finding_or_404(finding_id, db)
    rule = db.get(Rule, finding.rule_id)

    try:
        from core.llm_judge import LLMJudge, apply_llm_result_to_finding
        judge = LLMJudge()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    finding_dict = _finding_to_dict(finding, db, include_evidence=True)
    rule_dict = {
        "remediation": rule.remediation if rule else "",
        "rationale": rule.rationale if rule else "",
    }

    result = judge.analyze(finding_dict, rule_dict)
    apply_llm_result_to_finding(finding, result)
    db.commit()
    db.refresh(finding)
    return _finding_to_dict(finding, db, include_evidence=True)


@router.post(
    "/analyze-batch",
    responses={
        503: {"description": "LLM judge unavailable"},
        404: {"description": "One or more finding IDs not found (skipped silently)"},
    },
)
def analyze_batch(
    db: DB,
    finding_ids: Annotated[list[int], Body(description="List of finding IDs to analyze")],
) -> list[dict[str, Any]]:
    """
    Run the LLM judge on multiple findings. Returns results in order;
    failed items include an `llm_error` field instead.
    """
    try:
        from core.llm_judge import LLMJudge, apply_llm_result_to_finding
        judge = LLMJudge()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    items: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    findings: list[Finding] = []

    for fid in finding_ids:
        f = db.get(Finding, fid)
        if not f:
            continue
        rule = db.get(Rule, f.rule_id)
        items.append((
            _finding_to_dict(f, db, include_evidence=True),
            {"remediation": rule.remediation if rule else "",
             "rationale": rule.rationale if rule else ""},
        ))
        findings.append(f)

    results = judge.analyze_batch(items)

    output: list[dict[str, Any]] = []
    for finding, result in zip(findings, results):
        if isinstance(result, Exception):
            d = _finding_to_dict(finding, db)
            d["llm_error"] = str(result)
            output.append(d)
        else:
            apply_llm_result_to_finding(finding, result)
            output.append(_finding_to_dict(finding, db))

    db.commit()
    return output


# ── Ollama contextual remediation ─────────────────────────────────────────────

@router.post(
    "/{finding_id}/remediate",
    responses={
        404: {"description": "Finding not found"},
        503: {"description": "Ollama unavailable"},
    },
)
async def remediate_finding(finding_id: int, db: DB) -> dict[str, Any]:
    """
    Use Ollama (llama3.2) to generate a contextual remediation suggestion and
    impact factor (0.0–1.0) for a finding.  Persists results in the DB.
    """
    from core.llm_ollama import generate_impact_factor, generate_remediation

    finding = _get_finding_or_404(finding_id, db)
    rule = db.get(Rule, finding.rule_id)

    # Build posture context (open finding counts for the same platform)
    from sqlalchemy import func as sqlfunc
    crit = db.query(sqlfunc.count(Finding.id)).filter(
        Finding.platform == finding.platform,
        Finding.severity == "critical",
        Finding.status == "open",
    ).scalar() or 0
    high = db.query(sqlfunc.count(Finding.id)).filter(
        Finding.platform == finding.platform,
        Finding.severity == "high",
        Finding.status == "open",
    ).scalar() or 0
    total_open = db.query(sqlfunc.count(Finding.id)).filter(Finding.status == "open").scalar() or 0

    posture_ctx = {
        "critical_count": crit,
        "high_count": high,
        "total_open": total_open,
        "platform_summary": finding.platform,
    }

    finding_dict = _finding_to_dict(finding, db, include_evidence=True)
    finding_dict["remediation"] = rule.remediation if rule else ""

    try:
        remediation_text, rem_source, impact_val, expl_text, expl_source = await _run_ollama_all(finding_dict, posture_ctx)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ollama error: {exc}")

    finding.ollama_remediation = remediation_text
    finding.impact_factor = impact_val
    finding.generated_remediation = remediation_text
    finding.remediation_source = rem_source
    finding.impact_explanation = expl_text
    finding.impact_source = expl_source
    db.commit()
    db.refresh(finding)
    return _finding_to_dict(finding, db, include_evidence=False)


@router.post(
    "/{finding_id}/cia-impact",
    responses={404: {"description": "Finding not found"}},
)
async def get_cia_impact(finding_id: int, db: DB) -> dict[str, Any]:
    """
    Analyze CIA triad impact (Confidentiality, Integrity, Availability) for a finding using Ollama.
    Does not persist — returns analysis on demand.
    """
    import asyncio
    import logging as _log

    finding = _get_finding_or_404(finding_id, db)
    rule = db.get(Rule, finding.rule_id)

    rule_name = rule.name if rule else finding.rule_id
    prompt = (
        f"You are a cybersecurity expert. Analyze this security finding using the CIA triad "
        f"(Confidentiality, Integrity, Availability).\n\n"
        f"Finding: {rule_name}\n"
        f"Platform: {finding.platform}\n"
        f"Severity: {finding.severity}\n"
        f"Category: {finding.category or 'General'}\n"
        f"Description: {finding.description or ''}\n\n"
        f"For each CIA dimension write exactly 1-2 sentences on the concrete risk:\n"
        f"Confidentiality: how could this allow unauthorized access to or disclosure of sensitive data?\n"
        f"Integrity: how could this allow unauthorized modification of data, settings, or code?\n"
        f"Availability: how could this disrupt service continuity or system availability?\n\n"
        f"Respond in this exact format:\n"
        f"Confidentiality: <analysis>\n"
        f"Integrity: <analysis>\n"
        f"Availability: <analysis>"
    )

    try:
        from core.llm_ollama import _generate
        raw = await asyncio.wait_for(_generate(prompt), timeout=28.0)
        cia: dict[str, str] = {"confidentiality": "", "integrity": "", "availability": ""}
        for line in raw.strip().splitlines():
            for key in cia:
                if line.lower().startswith(f"{key}:"):
                    cia[key] = line[len(key) + 1:].strip()
        return {"finding_id": finding_id, "source": "ollama", **cia}
    except Exception as exc:
        _log.getLogger(__name__).warning("CIA impact failed for finding %s: %s", finding_id, exc)
        return {
            "finding_id": finding_id,
            "source": "static",
            **_static_cia_impact(finding.category or "", finding.severity or ""),
        }


def _static_cia_impact(category: str, severity: str) -> dict[str, str]:
    cat = category.lower()
    sev = severity.lower()
    risk = "high" if sev in ("critical", "high") else "moderate"

    if "auth" in cat or "mfa" in cat or "access" in cat:
        return {
            "confidentiality": f"An attacker who bypasses authentication gains {risk} read access to sensitive user data and secrets.",
            "integrity": "Unauthorized actors could modify records, settings, or code with no audit trail.",
            "availability": "Account takeover can lead to lockouts or deliberate disruption of services.",
        }
    if "secret" in cat or "credential" in cat or "token" in cat:
        return {
            "confidentiality": f"Exposed credentials provide {risk} access to protected data across systems.",
            "integrity": "Stolen tokens allow an attacker to make changes on behalf of the legitimate owner.",
            "availability": "Malicious actors could revoke or rotate credentials, causing service outages.",
        }
    if "branch" in cat or "code" in cat or "repo" in cat:
        return {
            "confidentiality": "Unprotected code repositories may expose proprietary logic and embedded secrets.",
            "integrity": f"Without branch protection, malicious or untested code can reach production — a {risk} integrity risk.",
            "availability": "Malicious merges could introduce bugs or backdoors that degrade or halt services.",
        }
    return {
        "confidentiality": f"This {sev}-severity finding may expose sensitive data to unauthorized parties.",
        "integrity": "Exploitation of this control gap could allow unauthorized modification of data or configuration.",
        "availability": "If exploited, this finding could contribute to service degradation or disruption.",
    }


async def _run_ollama_all(finding_dict: dict, posture_ctx: dict) -> tuple[str, str, float, str, str]:
    """Call all Ollama generators concurrently. Returns (rem_text, rem_src, impact, expl_text, expl_src)."""
    import asyncio
    from core.llm_ollama import generate_impact_explanation, generate_impact_factor, generate_remediation
    (rem_text, rem_src), impact, (expl_text, expl_src) = await asyncio.gather(
        generate_remediation(finding_dict, posture_ctx),
        generate_impact_factor(finding_dict, posture_ctx),
        generate_impact_explanation(finding_dict, posture_ctx),
    )
    return rem_text, rem_src, impact, expl_text, expl_src


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_status(value: str, valid: set[str]) -> None:
    if value not in valid:
        raise HTTPException(status_code=422, detail=f"Value must be one of {sorted(valid)}")


def _get_finding_or_404(finding_id: int, db: Session) -> Finding:
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")
    return finding


def _finding_to_dict(f: Finding, db: Session, include_evidence: bool = False) -> dict[str, Any]:
    rule = db.get(Rule, f.rule_id)
    d: dict[str, Any] = {
        "id": f.id,
        "rule_id": f.rule_id,
        "rule_name": rule.name if rule else None,
        "platform": f.platform,
        "connector_id": str(f.connector_id) if f.connector_id else None,
        "connector_name": f.connector_name,
        "resource_type": f.resource_type,
        "resource_identifier": f.resource_identifier,
        "severity": f.severity,
        "category": f.category,
        "description": f.description,
        "status": f.status,
        "justification": f.justification,
        "status_changed_at": f.status_changed_at.isoformat() if f.status_changed_at else None,
        "first_detected": f.first_detected.isoformat() if f.first_detected else None,
        "last_detected": f.last_detected.isoformat() if f.last_detected else None,
        "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
        "remediation": rule.remediation if rule else None,
        "compliance_mapping": rule.compliance_mapping if rule else [],
        # LLM fields
        "llm_severity": f.llm_severity,
        "llm_severity_reasoning": f.llm_severity_reasoning,
        "llm_exploitability": f.llm_exploitability,
        "llm_remediation": f.llm_remediation,
        "llm_confidence": f.llm_confidence,
        "llm_analyzed_at": f.llm_analyzed_at.isoformat() if f.llm_analyzed_at else None,
        # Ollama contextual fields
        "ollama_remediation": f.ollama_remediation,
        "impact_factor": f.impact_factor,
        "generated_remediation": f.generated_remediation,
        "remediation_source": f.remediation_source or "static",
        "impact_explanation": f.impact_explanation,
        "impact_source": f.impact_source or "static",
    }
    if include_evidence:
        d["evidence"] = f.evidence
    return d
