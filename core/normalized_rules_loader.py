"""
core/normalized_rules_loader.py — Load condition-based rule packs into the DB.

Handles rule YAML files with `query_type = "normalized"` (no Cypher/SQL query).
Each rule's `condition:` block is stored as JSONB in `rules.condition_json`.

Supported YAML structures
--------------------------
Two variants exist in the YAML files:

Variant A (CIS / ISO):
  rule_pack.rules[].id
  rule_pack.rules[].name          (or .title)
  rule_pack.rules[].severity
  rule_pack.rules[].description
  rule_pack.rules[].condition
  rule_pack.rules[].remediation   (dict with .summary, or plain string)

Variant B (NIST):
  rule_pack.rules[].id
  rule_pack.rules[].title
  rule_pack.rules[].severity
  rule_pack.rules[].condition
  rule_pack.rules[].remediation.message  (or .summary)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from database.models import Rule

log = logging.getLogger(__name__)


def _extract_remediation(rem: Any) -> str:
    if not rem:
        return ""
    if isinstance(rem, str):
        return rem
    if isinstance(rem, dict):
        summary = rem.get("summary") or rem.get("message") or ""
        steps: list[str] = rem.get("steps") or []
        if steps:
            lines = [summary] if summary else []
            lines += [f"- {s}" for s in steps]
            return "\n".join(lines)
        return summary
    return str(rem)


def _extract_compliance(rule_raw: dict, pack_meta: dict) -> list[str]:
    """Build a compact compliance reference list from the rule pack metadata."""
    framework = pack_meta.get("framework") or pack_meta.get("name") or ""
    # CIS: cis_safeguard.id
    cis = rule_raw.get("cis_safeguard") or {}
    if cis.get("id"):
        return [f"{framework} {cis['id']}"]
    # NIST: source_refs[].document + section
    refs = rule_raw.get("source_refs") or []
    if refs:
        parts = [f"{r.get('document', '')} §{r.get('section', '')}" for r in refs]
        return parts
    # ISO: mapped_controls at pack level — use scope field
    return [framework] if framework else []


def _extract_cis_control(rule_raw: dict, pack_meta: dict) -> str | None:
    cis = rule_raw.get("cis_safeguard") or {}
    if cis.get("id"):
        return f"CIS-{cis['id']}"
    framework = pack_meta.get("framework") or ""
    if "ISO" in framework.upper():
        return "ISO27001"
    if "NIST" in framework.upper():
        return "NIST-800-63"
    return None


def _extract_referentials(pack_meta: dict) -> list[str]:
    """Derive the standards list from the framework name in rule pack metadata."""
    framework = (pack_meta.get("framework") or pack_meta.get("name") or "").upper()
    refs: list[str] = []
    if "CIS" in framework:
        refs.append("CIS")
    if "ISO" in framework or "27001" in framework:
        refs.append("ISO27001")
    if "NIST" in framework:
        refs.append("NIST")
    if "SOC" in framework:
        refs.append("SOC2")
    return refs or ["custom"]


def _rule_platform(pack_meta: dict) -> str:
    """Normalized rules apply cross-platform — use 'all' as the platform tag."""
    return "all"


def load_rule_pack(yaml_path: Path, db: Session, *, overwrite: bool = True) -> int:
    """
    Parse a normalized rule YAML file and upsert rules into the DB.

    Returns the number of rules written.
    """
    with yaml_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    pack = data.get("rule_pack") or data
    rules_raw: list[dict] = pack.get("rules") or data.get("rules") or []

    if not rules_raw:
        log.warning("No rules found in %s", yaml_path)
        return 0

    written = 0
    for raw in rules_raw:
        if not raw.get("enabled", True):
            continue

        rule_id: str = str(raw.get("id", ""))
        if not rule_id:
            log.warning("Skipping rule without id in %s", yaml_path)
            continue

        name: str = raw.get("name") or raw.get("title") or rule_id
        severity: str = str(raw.get("severity", "medium")).lower()
        description: str = raw.get("description") or ""
        condition: dict | None = raw.get("condition")
        remediation_text = _extract_remediation(raw.get("remediation"))
        compliance = _extract_compliance(raw, pack)
        cis_control = _extract_cis_control(raw, pack)
        referentials = _extract_referentials(pack)

        category_raw = raw.get("category") or raw.get("cis_safeguard", {}).get("title") or "access_control"
        category = str(category_raw).lower().replace(" ", "_")[:64]

        existing: Rule | None = db.get(Rule, rule_id)

        if existing and not overwrite:
            continue

        if existing:
            existing.name = name
            existing.severity = severity
            existing.description = description
            existing.condition_json = condition
            existing.remediation = remediation_text
            existing.compliance_mapping = compliance
            existing.cis_control = cis_control
            existing.category = category
            existing.query_type = "normalized"
            existing.detection_query = None
            existing.platform = _rule_platform(pack)
            existing.referentials = referentials
        else:
            db.add(Rule(
                id=rule_id,
                name=name,
                platform=_rule_platform(pack),
                cis_control=cis_control,
                severity=severity,
                category=category,
                description=description,
                condition_json=condition,
                query_type="normalized",
                detection_query=None,
                remediation=remediation_text,
                compliance_mapping=compliance,
                referentials=referentials,
                is_active=True,
            ))

        written += 1

    db.flush()
    log.info("Loaded %d normalized rules from %s", written, yaml_path.name)
    return written
