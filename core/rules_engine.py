"""
Universal Rules Engine – executes detection rules stored in the DB.

For each active rule it:
  1. Runs its Cypher query against Neo4j (or SQL against PostgreSQL)
  2. Turns every result row into a Finding
  3. Deduplicates: open finding for same (rule_id, resource_identifier) → update last_detected
  4. Returns a summary dict

Platform-specific logic lives entirely in the connector and the Cypher queries.
The engine itself is platform-agnostic.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from core.graph_manager import GraphManager
from database.models import Finding, Rule

log = logging.getLogger(__name__)


class RulesEngine:
    """Execute DB-stored detection rules and persist findings."""

    def __init__(
        self,
        db: Session,
        graph: GraphManager,
        connector_id: str | None = None,
        connector_name: str | None = None,
    ):
        self._db = db
        self._graph = graph
        self._connector_id = connector_id
        self._connector_name = connector_name

    # ── Public API ────────────────────────────────────────────────────────────

    def run_all_rules(self, platform: str | None = None, scan_run_id: str | None = None) -> dict[str, Any]:
        """
        Execute all active rules, optionally filtered by platform.

        Returns a summary dict:
          {total_rules, total_findings, new_findings, updated_findings, by_severity, errors}
        """
        query = self._db.query(Rule).filter(Rule.is_active == True)  # noqa: E712
        if platform:
            query = query.filter(Rule.platform == platform)
        rules = query.order_by(Rule.severity, Rule.id).all()

        summary: dict[str, Any] = {
            "total_rules": len(rules),
            "total_findings": 0,
            "new_findings": 0,
            "updated_findings": 0,
            "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "errors": [],
        }

        for rule in rules:
            try:
                new, updated = self._run_rule(rule, scan_run_id)
                summary["new_findings"] += new
                summary["updated_findings"] += updated
                summary["total_findings"] += new + updated
                for sev, cnt in self._count_open_by_severity(rule.id).items():
                    summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + cnt
            except Exception as exc:
                log.warning("rule_execution_error", extra={"rule_id": rule.id, "error": str(exc)})
                summary["errors"].append({"rule_id": rule.id, "error": str(exc)})

        # Run condition-based normalized rules (cross-platform, no Cypher/SQL)
        try:
            from core.normalized_rules_engine import run_normalized_rules
            norm_new = run_normalized_rules(
                self._db,
                connector_id=self._connector_id,
                platform=platform,
                scan_run_id=scan_run_id,
            )
            summary["new_findings"] += norm_new
            summary["total_findings"] += norm_new
        except Exception as exc:
            log.warning("normalized_rules_error", extra={"error": str(exc)})
            summary["errors"].append({"rule_id": "normalized_engine", "error": str(exc)})

        self._db.commit()
        log.info("rules_engine_done", extra=summary)
        return summary

    def run_rule(self, rule_id: str, scan_run_id: str | None = None) -> list[Finding]:
        """Execute a single rule by ID. Returns list of findings (new + updated)."""
        rule = self._db.get(Rule, rule_id)
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")
        self._run_rule(rule, scan_run_id)
        self._db.commit()
        return (
            self._db.query(Finding)
            .filter(Finding.rule_id == rule_id, Finding.status == "open")
            .all()
        )

    # ── Execution ─────────────────────────────────────────────────────────────

    def _run_rule(self, rule: Rule, scan_run_id: str | None) -> tuple[int, int]:
        """Execute rule, upsert findings. Returns (new_count, updated_count)."""
        rows = self._execute_query(rule)
        if not rows:
            return 0, 0

        new_count = updated_count = 0
        for row in rows:
            resource_id = self._extract_identifier(row, rule.resource_id_field)
            if not resource_id:
                continue
            new, updated = self._upsert_finding(
                rule, resource_id, row, scan_run_id,
                self._connector_id, self._connector_name,
            )
            new_count += new
            updated_count += updated

        return new_count, updated_count

    def _execute_query(self, rule: Rule) -> list[dict[str, Any]]:
        """Dispatch to the right query executor."""
        if rule.query_type == "normalized":
            return []  # handled separately by run_normalized_rules
        if rule.query_type == "cypher":
            return self._execute_cypher(rule.detection_query)
        if rule.query_type == "sql":
            return self._execute_sql(rule.detection_query)
        raise ValueError(f"Unknown query_type: {rule.query_type!r}")

    def _execute_cypher(self, query: str) -> list[dict[str, Any]]:
        with self._graph._session() as session:
            result = session.run(query)
            return [dict(record) for record in result]

    def _execute_sql(self, query: str) -> list[dict[str, Any]]:
        rows = self._db.execute(__import__("sqlalchemy").text(query))
        return [dict(r._mapping) for r in rows]

    # ── Deduplication ─────────────────────────────────────────────────────────

    def _upsert_finding(
        self,
        rule: Rule,
        resource_identifier: str,
        evidence: dict[str, Any],
        scan_run_id: str | None,
        connector_id: str | None = None,
        connector_name: str | None = None,
    ) -> tuple[int, int]:
        """
        Insert or update a finding with incremental-sync state preservation.

        Dedup key: (rule_id, resource_identifier, connector_id)
        Falls back to matching unattributed findings (connector_id IS NULL) to
        avoid creating duplicates for findings created before connector tracking.

        State machine:
          - No existing finding       → create new "open" finding
          - Existing status "open"    → update last_detected + evidence
          - Existing status "resolved"→ re-open (issue re-detected)
          - Existing status "accepted_risk" / "false_positive"
                                      → keep status & justification, update last_detected

        Returns (new_count, updated_count).
        """
        from sqlalchemy import or_
        now = datetime.now(timezone.utc)

        base_filter = [
            Finding.rule_id == rule.id,
            Finding.resource_identifier == resource_identifier,
        ]

        # Try exact connector match first, then fall back to unattributed findings
        # (backwards compat: findings created before connector_id column was added)
        existing = None
        if connector_id:
            existing = (
                self._db.query(Finding)
                .filter(*base_filter, Finding.connector_id == connector_id)
                .order_by(Finding.first_detected.desc())
                .first()
            )
            if not existing:
                existing = (
                    self._db.query(Finding)
                    .filter(*base_filter, Finding.connector_id.is_(None))
                    .order_by(Finding.first_detected.desc())
                    .first()
                )
        else:
            existing = (
                self._db.query(Finding)
                .filter(*base_filter)
                .order_by(Finding.first_detected.desc())
                .first()
            )

        if existing:
            if existing.status == "resolved":
                # Re-detected after being resolved → re-open
                existing.status = "open"
                existing.status_changed_at = now
                existing.resolved_at = None
                existing.justification = None
            # For accepted_risk / false_positive: keep status + justification as-is
            existing.last_detected = now
            existing.evidence = evidence
            if scan_run_id:
                existing.scan_run_id = scan_run_id
            # Backfill connector attribution on legacy unattributed findings
            if connector_id and not existing.connector_id:
                existing.connector_id = connector_id
                existing.connector_name = connector_name
            return 0, 1

        finding = Finding(
            rule_id=rule.id,
            connector_id=connector_id,
            connector_name=connector_name,
            platform=rule.platform,
            resource_type=self._infer_resource_type(rule.resource_id_field),
            resource_identifier=resource_identifier,
            resource_name=str(evidence.get(rule.resource_id_field, resource_identifier)),
            severity=rule.severity,
            category=rule.category,
            description=self._build_description(rule, evidence),
            evidence=evidence,
            status="open",
            first_detected=now,
            last_detected=now,
            scan_run_id=scan_run_id,
        )
        self._db.add(finding)
        return 1, 0

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_identifier(row: dict[str, Any], field: str) -> str:
        """Pull the resource identifier from a query result row."""
        val = row.get(field)
        if val is not None:
            return str(val)
        # Fall back to first non-None string value
        for v in row.values():
            if v is not None and isinstance(v, str):
                return v
        return str(list(row.values())[0]) if row else ""

    @staticmethod
    def _infer_resource_type(resource_id_field: str) -> str:
        mapping = {
            "repository": "repository",
            "user": "user",
            "external_user": "user",
            "organization": "org",
            "application": "application",
        }
        return mapping.get(resource_id_field, resource_id_field)

    @staticmethod
    def _build_description(rule: Rule, evidence: dict[str, Any]) -> str:
        """Build a human-readable description enriched with evidence."""
        base = rule.description or rule.name
        resource = evidence.get(rule.resource_id_field, "")
        if resource:
            return f"{base} — affected: {resource}"
        return base

    def _count_open_by_severity(self, rule_id: str) -> dict[str, int]:
        from sqlalchemy import func
        rows = (
            self._db.query(Finding.severity, func.count(Finding.id))
            .filter(Finding.rule_id == rule_id, Finding.status == "open")
            .group_by(Finding.severity)
            .all()
        )
        return dict(rows)
