"""
/posture — Security posture score endpoints.

Posture formula (impact-weighted deduction model):
  score = 100 - (Σ severity_weight × impact_factor / max_possible × 100)

Severity weights: critical=10, high=7, medium=4, low=1
impact_factor per finding: float 0.0–1.0 (default 0.5, updated by Ollama)
max_possible: number_of_open_findings × 10  (all critical, max impact)
"""
import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy.orm import joinedload

from database.models import Finding, Rule
from database.session import get_db

log = logging.getLogger(__name__)

router = APIRouter(prefix="/posture", tags=["posture"])

DB = Annotated[Session, Depends(get_db)]

_SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 10.0,
    "high": 7.0,
    "medium": 4.0,
    "low": 1.0,
}


def _compute_score(findings: list[Finding]) -> float:
    """Apply the impact-weighted deduction formula. Returns 0.0–100.0."""
    if not findings:
        return 100.0

    total_weight = sum(
        _SEVERITY_WEIGHTS.get(f.severity, 1.0) * (f.impact_factor if f.impact_factor is not None else 0.5)
        for f in findings
    )
    max_possible = len(findings) * 10.0  # all critical at max impact
    deduction = (total_weight / max_possible) * 100.0
    return round(max(0.0, 100.0 - deduction), 1)


ScorePlatform = Annotated[str | None, Query(description="Filter by platform")]
ConnectorId = Annotated[str | None, Query(description="Filter by connector UUID")]


@router.get("/score")
def get_posture_score(
    db: DB,
    platform: ScorePlatform = None,
    connector_id: ConnectorId = None,
) -> dict[str, Any]:
    """
    Return the overall security posture score (0–100) and per-severity breakdown.

    Uses impact_factor per finding (populated by Ollama, defaults to 0.5).
    """
    q = select(Finding).where(Finding.status == "open")
    if platform:
        q = q.where(Finding.platform == platform)
    if connector_id:
        q = q.where(Finding.connector_id == connector_id)

    findings: list[Finding] = list(db.execute(q).scalars())

    score = _compute_score(findings)

    # Breakdown by severity
    by_severity: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        if f.severity in by_severity:
            by_severity[f.severity] += 1

    # Count findings without Ollama analysis yet (impact_factor is still default)
    pending_analysis = sum(1 for f in findings if f.ollama_remediation is None)

    return {
        "score": score,
        "total_open_findings": len(findings),
        "by_severity": by_severity,
        "pending_ollama_analysis": pending_analysis,
        "formula": "100 - (Σ severity_weight × impact_factor / max_possible × 100)",
        "filters": {"platform": platform, "connector_id": connector_id},
    }


# ── Prioritized Actions ───────────────────────────────────────────────────────

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _deterministic_actions(findings: list[Finding], limit: int) -> list[dict]:
    """Rank findings by severity + impact_factor and return structured actions."""
    ranked = sorted(
        findings,
        key=lambda f: (
            _SEV_ORDER.get(f.severity, 4),
            -(f.impact_factor if f.impact_factor is not None else 0.5),
        ),
    )
    actions = []
    for i, f in enumerate(ranked[:limit], start=1):
        rule_name = (f.rule.name if f.rule else None) or f.rule_id or "Unknown rule"
        actions.append({
            "rank": i,
            "finding_id": f.id,
            "rule_id": f.rule_id,
            "title": rule_name,
            "severity": f.severity,
            "platform": f.platform,
            "resource_identifier": f.resource_identifier,
            "impact_factor": round(f.impact_factor if f.impact_factor is not None else 0.5, 2),
            "impact_summary": f.impact_explanation or f.description or "",
            "recommended_action": f.generated_remediation or (f.rule.remediation if f.rule else None) or "Review rule documentation.",
        })
    return actions


def _ollama_actions_prompt(top_findings: list[Finding], posture_score: float) -> str:
    items = []
    for i, f in enumerate(top_findings, start=1):
        items.append(
            f"{i}. [{f.severity.upper()}] {(f.rule.name if f.rule else None) or f.rule_id} "
            f"on {f.platform}/{f.resource_identifier or 'unknown'} "
            f"(impact={round(f.impact_factor or 0.5, 2)})"
        )
    findings_list = "\n".join(items)

    return f"""You are a SaaS security advisor. Current posture score: {posture_score}/100.

Top open security findings (by priority):
{findings_list}

Return a JSON array of up to {len(top_findings)} prioritized actions. Each action must have:
  "rank": integer starting at 1,
  "title": short action title (max 60 chars),
  "severity": one of critical/high/medium/low,
  "platform": the platform string,
  "finding_id": the finding id from the list index (1-based),
  "impact_summary": 1 sentence on the risk,
  "recommended_action": 1–2 sentence fix.

Reply with ONLY the JSON array. No markdown, no explanation."""


async def _try_ollama_actions(
    findings: list[Finding], score: float, limit: int
) -> tuple[list[dict], str]:
    """Attempt to get Ollama-ranked actions. Returns (actions, source)."""
    from core.llm_ollama import _ENABLED, _generate  # noqa: PLC0415

    if not _ENABLED or not findings:
        return _deterministic_actions(findings, limit), "deterministic"

    top = sorted(
        findings,
        key=lambda f: (
            _SEV_ORDER.get(f.severity, 4),
            -(f.impact_factor if f.impact_factor is not None else 0.5),
        ),
    )[:limit]

    try:
        raw = await _generate(_ollama_actions_prompt(top, score))
        # Extract first JSON array from the response
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            raise ValueError("No JSON array in response")
        parsed: list[dict] = json.loads(raw[start : end + 1])
        if not isinstance(parsed, list):
            raise ValueError("Expected JSON array")
        # Resolve finding_id back to real IDs using rank as index
        for item in parsed:
            rank = item.get("finding_id", 1)
            if isinstance(rank, int) and 1 <= rank <= len(top):
                item["finding_id"] = top[rank - 1].id
        return parsed, "ollama"
    except Exception as exc:
        log.warning("Ollama prioritized actions failed: %s", exc)
        return _deterministic_actions(findings, limit), "deterministic"


Platform = Annotated[str | None, Query(description="Filter by platform")]
Limit = Annotated[int, Query(ge=1, le=20, description="Max actions to return")]


@router.post("/prioritized-actions")
async def get_prioritized_actions(
    db: DB,
    platform: Platform = None,
    limit: Limit = 5,
) -> dict[str, Any]:
    """
    Return AI-prioritized remediation actions for the top open findings.

    Uses Ollama to rank and explain actions. Falls back to deterministic
    severity+impact_factor ranking if Ollama is unavailable.
    """
    q = select(Finding).where(Finding.status == "open").options(joinedload(Finding.rule))
    if platform:
        q = q.where(Finding.platform == platform)
    findings: list[Finding] = list(db.execute(q).scalars())

    score = _compute_score(findings)
    actions, source = await _try_ollama_actions(findings, score, limit)

    return {
        "actions": actions,
        "total_open_findings": len(findings),
        "posture_score": score,
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
