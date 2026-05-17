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
from datetime import datetime, timezone
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

    def snapshot_all(self, db: Session) -> None:
        """Persist a ComplianceSnapshot for every platform × framework with mapped rules."""
        try:
            from database.models import Connector
            rule_platforms = {row[0] for row in db.query(distinct(Rule.platform)).all() if row[0] != "cross-platform"}
            connector_platforms = {row[0] for row in db.query(distinct(Connector.platform_name)).all()}
            platforms = list(rule_platforms | connector_platforms)
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
