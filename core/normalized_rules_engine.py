"""
core/normalized_rules_engine.py — Condition-based rule evaluation over NormalizedEntity.

Evaluates rules with query_type="normalized" against the canonical `attributes.*`
block written by core/normalization.py.  No Cypher or SQL queries are used — all
logic runs in Python against the JSONB `data_json` already loaded from PostgreSQL.

Operators
---------
equals / not_equals     — strict equality
exists / not_exists     — key presence check
is_empty                — None or empty string/list
older_than_days N       — datetime value is more than N days in the past
older_than_now          — datetime value is in the past (revocation_due_at logic)
contains                — list contains value
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Finding, NormalizedEntity, Rule

log = logging.getLogger(__name__)

# Severity → integer weight (used only for posture score elsewhere, not here)
_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


# ---------------------------------------------------------------------------
# Field accessor — supports "attributes.foo" dot notation
# ---------------------------------------------------------------------------

def _get_field(data_json: dict, field: str) -> tuple[Any, bool]:
    """
    Return (value, exists).  Supports dot notation into nested dicts.
    """
    parts = field.split(".", 1)
    if len(parts) == 1:
        exists = field in data_json
        return data_json.get(field), exists

    top, rest = parts
    child = data_json.get(top)
    if not isinstance(child, dict):
        return None, False
    return _get_field(child, rest)


# ---------------------------------------------------------------------------
# Single-condition evaluator
# ---------------------------------------------------------------------------

def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _days_ago(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def _eval_leaf(data_json: dict, cond: dict) -> bool:
    field: str = cond.get("field", "")
    operator: str = cond.get("operator", "equals")
    expected = cond.get("value")

    value, exists = _get_field(data_json, field)

    if operator == "exists":
        return exists and value is not None
    if operator == "not_exists":
        return not exists or value is None
    if operator == "is_empty":
        if not exists or value is None:
            return True
        if isinstance(value, (list, str)):
            return len(value) == 0
        return False
    if operator == "equals":
        return value == expected
    if operator == "not_equals":
        return value != expected
    if operator == "contains":
        if isinstance(value, list):
            return expected in value
        return False
    if operator in ("older_than_days", "older_than_now"):
        dt = _parse_iso(value) if isinstance(value, str) else None
        if dt is None:
            return False
        days = _days_ago(dt)
        if days is None:
            return False
        if operator == "older_than_now":
            return days > 0
        return days > int(expected or 0)

    log.debug("Unknown operator %r — treating as False", operator)
    return False


# ---------------------------------------------------------------------------
# Recursive condition evaluator (all / any / leaf)
# ---------------------------------------------------------------------------

def _eval_condition(data_json: dict, cond: dict) -> bool:  # noqa: C901
    if "all" in cond:
        return all(_eval_condition(data_json, c) for c in cond["all"])
    if "any" in cond:
        return any(_eval_condition(data_json, c) for c in cond["any"])
    if "field" in cond:
        return _eval_leaf(data_json, cond)
    # Unknown shape — default to False (safe)
    log.debug("Unrecognised condition node: %s", cond)
    return False


# ---------------------------------------------------------------------------
# Finding builder
# ---------------------------------------------------------------------------

def _build_evidence(data_json: dict, evidence_fields: list[str]) -> dict:
    evidence: dict[str, Any] = {}
    for f in evidence_fields:
        val, exists = _get_field(data_json, f)
        if exists:
            evidence[f] = val
    return evidence


def _resource_identifier(entity: NormalizedEntity) -> str:
    dj = entity.data_json or {}
    return (
        dj.get("email")
        or dj.get("username")
        or dj.get("name")
        or entity.platform_id
    )


def _resource_name(entity: NormalizedEntity) -> str:
    dj = entity.data_json or {}
    return dj.get("display_name") or dj.get("name") or entity.platform_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_normalized_rules(
    db: Session,
    connector_id: str | None = None,
    platform: str | None = None,
    scan_run_id: str | None = None,
) -> int:
    """
    Evaluate all active normalized rules against entities in the DB.

    Scope can be narrowed by connector_id or platform.
    Returns the total number of new findings created.
    """
    # Load active normalized rules
    rules_q = select(Rule).where(
        Rule.is_active.is_(True),
        Rule.query_type == "normalized",
        Rule.condition_json.isnot(None),
    )
    rules: list[Rule] = list(db.execute(rules_q).scalars())

    if not rules:
        log.info("No active normalized rules found.")
        return 0

    # Load entities to evaluate
    entities_q = select(NormalizedEntity).where(
        NormalizedEntity.entity_type.in_(["user", "group", "org"])
    )
    if platform:
        entities_q = entities_q.where(NormalizedEntity.platform == platform)

    entities: list[NormalizedEntity] = list(db.execute(entities_q).scalars())
    log.info("Evaluating %d normalized rules against %d entities", len(rules), len(entities))

    new_findings = 0

    for rule in rules:
        condition = rule.condition_json
        for entity in entities:
            dj = entity.data_json or {}
            if not dj.get("attributes"):
                continue  # entity not yet normalized — skip

            try:
                matched = _eval_condition(dj, condition)
            except Exception:
                log.exception("Error evaluating rule %s on entity %s", rule.id, entity.id)
                continue

            if not matched:
                continue

            # Dedup: skip if an open finding already exists for this rule + entity
            existing = db.execute(
                select(Finding).where(
                    Finding.rule_id == rule.id,
                    Finding.resource_identifier == entity.platform_id,
                    Finding.status == "open",
                )
            ).scalar_one_or_none()

            if existing:
                existing.last_detected = datetime.now(timezone.utc)
                continue

            finding = Finding(
                rule_id=rule.id,
                connector_id=connector_id,
                platform=entity.platform,
                resource_type=entity.entity_type,
                resource_identifier=entity.platform_id,
                resource_name=_resource_name(entity),
                severity=rule.severity,
                category=rule.category,
                description=rule.description or rule.name,
                evidence=_build_evidence(dj, []),
                status="open",
                scan_run_id=scan_run_id,
                impact_factor=0.5,
            )
            db.add(finding)
            new_findings += 1

    db.flush()
    log.info("Normalized rules engine: %d new findings created", new_findings)
    return new_findings
