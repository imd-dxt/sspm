"""
/connectors  –  CRUD, sync, and status endpoints for SaaS connectors.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from sqlalchemy import func
from database.models import Connector, Finding, ScanRun
from database.schemas import ConnectorCreate, ConnectorResponse, ConnectorStatusResponse, ConnectorScheduleRequest, ScanRunResponse
from database.session import get_db
from utils.crypto import encrypt, decrypt

log = logging.getLogger(__name__)
router = APIRouter(prefix="/connectors", tags=["connectors"])

DB = Annotated[Session, Depends(get_db)]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_connector_or_404(connector_id: str, db: Session) -> Connector:
    obj = db.query(Connector).filter(Connector.id == connector_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Connector not found")
    return obj


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_connector(payload: ConnectorCreate, db: DB) -> Connector:
    """Register a new SaaS connector. Credentials are encrypted at rest."""
    encrypted = encrypt(json.dumps(payload.credentials))
    obj = Connector(
        platform_name=payload.platform_name,
        display_name=payload.display_name,
        credentials_encrypted=encrypted,
        config_json=payload.config,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log.info("connector_created", extra={"id": obj.id, "platform": obj.platform_name})
    return obj


@router.get("/", response_model=list[ConnectorResponse])
def list_connectors(db: DB) -> list[Connector]:
    """List all registered connectors."""
    return db.query(Connector).order_by(Connector.created_at.desc()).all()


@router.get(
    "/{connector_id}",
    response_model=ConnectorResponse,
    responses={404: {"description": "Connector not found"}},
)
def get_connector(connector_id: str, db: DB) -> Connector:
    return _get_connector_or_404(connector_id, db)


@router.delete(
    "/{connector_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Connector not found"}},
)
def delete_connector(connector_id: str, db: DB) -> None:
    obj = _get_connector_or_404(connector_id, db)

    # Delete findings attributed to this connector (findings.connector_id FK)
    db.query(Finding).filter(Finding.connector_id == connector_id).delete(synchronize_session=False)

    # Null out scan_run_id on any remaining findings referencing this connector's
    # scan runs (edge case: findings without connector_id attribution)
    scan_run_ids = [
        r[0] for r in db.query(ScanRun.id).filter(ScanRun.connector_id == connector_id).all()
    ]
    if scan_run_ids:
        db.query(Finding).filter(Finding.scan_run_id.in_(scan_run_ids)).update(
            {"scan_run_id": None}, synchronize_session=False
        )

    db.delete(obj)  # ORM cascade deletes scan_runs
    db.commit()


# ── Status ────────────────────────────────────────────────────────────────────

@router.get(
    "/{connector_id}/status",
    responses={404: {"description": "Connector not found"}},
)
def get_connector_status(connector_id: str, db: DB) -> ConnectorStatusResponse:
    """
    Return the last connection health for a connector
    (populated after each sync or test).
    """
    obj = _get_connector_or_404(connector_id, db)
    return ConnectorStatusResponse(
        connector_id=obj.id,
        platform_name=obj.platform_name,
        display_name=obj.display_name,
        connection_ok=obj.connection_ok,
        last_sync_at=obj.last_sync_at,
        last_sync_error=obj.last_sync_error,
    )


# ── Test ──────────────────────────────────────────────────────────────────────

@router.get(
    "/{connector_id}/test",
    responses={
        404: {"description": "Connector not found"},
        400: {"description": "Unknown platform"},
    },
)
def test_connector(connector_id: str, db: DB) -> dict[str, Any]:
    """Test connectivity for a registered connector. Updates connection_ok on the connector."""
    obj = _get_connector_or_404(connector_id, db)
    credentials = json.loads(decrypt(obj.credentials_encrypted))

    if obj.platform_name == "github":
        from connectors.github_connector import GitHubConnector
        result = GitHubConnector(credentials=credentials, config=obj.config_json).test_connection()
    elif obj.platform_name == "jira":
        from connectors.jira_connector import JiraConnector
        result = JiraConnector(credentials=credentials, config=obj.config_json).test_connection()
    elif obj.platform_name == "salesforce":
        from connectors.salesforce_connector import SalesforceConnector
        result = SalesforceConnector(credentials=credentials, config=obj.config_json).test_connection()
    elif obj.platform_name == "entraid":
        from connectors.entraid_connector import EntraIDConnector
        result = EntraIDConnector(credentials=credentials, config=obj.config_json).test_connection()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {obj.platform_name}")

    # Persist the test outcome so the connector card reflects the real status
    _update_connector_health(obj, ok=result.get("ok", False), error=result.get("error"))
    db.commit()
    return result


# ── Sync ──────────────────────────────────────────────────────────────────────

@router.post(
    "/{connector_id}/sync",
    response_model=ScanRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"description": "Connector not found"},
        400: {"description": "Unknown platform"},
    },
)
def trigger_sync(connector_id: str, db: DB, background_tasks: BackgroundTasks) -> ScanRun:
    """
    Trigger a synchronous scan for the connector.

    NOTE: In production move this to a background task queue (Celery/ARQ).
          Phase 1 runs synchronously for simplicity.
    """
    obj = _get_connector_or_404(connector_id, db)
    credentials = json.loads(decrypt(obj.credentials_encrypted))

    # Create scan run record
    scan_run = ScanRun(
        connector_id=connector_id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(scan_run)
    db.commit()
    db.refresh(scan_run)

    try:
        connector, neo4j_org_id = _build_connector(obj.platform_name, credentials, obj.config_json)

        from core.graph_manager import GraphManager
        from core.rules_engine import RulesEngine

        progress = connector.sync()
        entities = getattr(progress, "entities", [])
        _update_connector_health(obj, ok=True, error=None)

        _persist_entities(db, entities)
        _sync_neo4j(entities, neo4j_org_id, obj.platform_name, progress)
        _persist_audit_logs(connector, obj.platform_name, str(obj.id), db, progress)

        # Run rules engine — pass connector attribution so findings are stamped
        gm_rules = GraphManager()
        findings_count = 0
        try:
            engine = RulesEngine(db=db, graph=gm_rules, connector_id=str(obj.id), connector_name=obj.display_name)
            engine.run_all_rules(platform=obj.platform_name, scan_run_id=str(scan_run.id))
            findings_count = (
                db.query(func.count(Finding.id))
                .filter(Finding.connector_id == str(obj.id), Finding.status == "open")
                .scalar() or 0
            )
            scan_run.findings_count = findings_count
        except Exception as rules_exc:
            log.warning("rules_engine_error", extra={"error": str(rules_exc)})
            progress.record_error("rules_engine", str(rules_exc))
        finally:
            gm_rules.close()

        scan_run.status = progress.status
        scan_run.completed_at = progress.completed_at
        scan_run.records_fetched = progress.records_fetched
        scan_run.errors_json = progress.errors

        db.commit()
        db.refresh(scan_run)

        try:
            from core.compliance_engine import ComplianceEngine
            ComplianceEngine().snapshot_all(db, scan_run_id=str(scan_run.id))
        except Exception as snap_exc:
            log.warning("compliance_snapshot_error: %s", snap_exc)

        background_tasks.add_task(_bg_post_sync, obj.platform_name, str(scan_run.id))
        return scan_run

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("sync_failed", extra={"connector_id": connector_id})
        _update_connector_health(obj, ok=False, error=str(exc))
        db.rollback()
        scan_run.status = "failed"
        scan_run.completed_at = datetime.now(timezone.utc)
        scan_run.errors_json = [{"error": str(exc)}]
        # Re-add scan_run after rollback wiped it, then log failure
        db.add(scan_run)
        db.commit()
        db.refresh(scan_run)
        return scan_run


# ── Background post-sync tasks ────────────────────────────────────────────────

async def _bg_post_sync(platform: str, scan_run_id: str) -> None:
    """
    Runs after every successful sync (as a FastAPI BackgroundTask):
    1. Auto-generate AI remediation + impact for new open findings.
    2. Pre-generate compliance reports for all frameworks so admins can download immediately.
    """
    import asyncio
    from database.session import SessionLocal
    from database.models import Finding, Rule
    from core.compliance_engine import FRAMEWORKS

    log.info("bg_post_sync: start platform=%s scan=%s", platform, scan_run_id)

    # ── 1. Generate remediations for new findings ─────────────────────────────
    db0 = SessionLocal()
    try:
        new_findings = db0.query(Finding).filter(
            Finding.scan_run_id == scan_run_id,
            Finding.status == "open",
            Finding.generated_remediation.is_(None),
        ).all()
        finding_ids = [f.id for f in new_findings]
        # build per-platform posture context once
        from sqlalchemy import func as sqlfunc
        crit = db0.query(sqlfunc.count(Finding.id)).filter(Finding.platform == platform, Finding.severity == "critical", Finding.status == "open").scalar() or 0
        high = db0.query(sqlfunc.count(Finding.id)).filter(Finding.platform == platform, Finding.severity == "high", Finding.status == "open").scalar() or 0
        total_open = db0.query(sqlfunc.count(Finding.id)).filter(Finding.status == "open").scalar() or 0
        posture_ctx = {"critical_count": crit, "high_count": high, "total_open": total_open, "platform_summary": platform}
    finally:
        db0.close()

    sem = asyncio.Semaphore(2)

    async def _gen_finding_remediation(finding_id: int) -> None:
        async with sem:
            db2 = SessionLocal()
            try:
                f = db2.get(Finding, finding_id)
                if not f or f.generated_remediation:
                    return
                rule = db2.get(Rule, f.rule_id)
                from api.routes.findings import _finding_to_dict, _run_ollama_all
                fd = _finding_to_dict(f, db2, include_evidence=True)
                fd["remediation"] = rule.remediation if rule else ""
                rem_text, rem_src, impact_val, expl_text, expl_src = await asyncio.wait_for(
                    _run_ollama_all(fd, posture_ctx), timeout=45.0
                )
                f.generated_remediation = rem_text
                f.remediation_source = rem_src
                f.impact_factor = impact_val
                f.impact_explanation = expl_text
                f.impact_source = expl_src
                db2.commit()
            except Exception as exc:
                log.warning("bg_gen_remediation finding=%s: %s", finding_id, exc)
            finally:
                db2.close()

    if finding_ids:
        await asyncio.gather(*[_gen_finding_remediation(fid) for fid in finding_ids], return_exceptions=True)
        log.info("bg_post_sync: remediated %d findings", len(finding_ids))

    # ── 2. Pre-generate compliance reports for every framework ─────────────────
    from core.compliance_engine import ComplianceEngine
    from database.models import ComplianceReport as DbReport
    from sqlalchemy import distinct
    from database.models import Connector

    for framework in FRAMEWORKS:
        for target_platform in (platform, "all"):
            try:
                db3 = SessionLocal()
                try:
                    engine = ComplianceEngine()
                    # Collect platforms for aggregation
                    if target_platform == "all":
                        platforms_list = [
                            row[0] for row in db3.query(distinct(Connector.platform_name))
                            .filter(Connector.connection_ok.is_(True)).all()
                        ]
                    else:
                        platforms_list = [target_platform]

                    if not platforms_list:
                        continue

                    total_rules = passed_rules = failed_rules = 0
                    for plat in platforms_list:
                        r = engine.calculate_score(plat, framework, db3)
                        total_rules += r["total_rules"]
                        passed_rules += r["passed_rules"]
                        failed_rules += r["failed_rules"]

                    if total_rules == 0:
                        continue

                    covered = passed_rules + failed_rules
                    score = round((passed_rules / covered) * 100) if covered > 0 else 100

                    # Generate narrative via Ollama
                    from api.routes.compliance import _collect_failing_rules, FRAMEWORKS as FW_MAP
                    failing = _collect_failing_rules(platforms_list, framework, db3)
                    fw_name = FW_MAP.get(framework, {}).get("name", framework)
                    from core.llm_ollama import _generate as _ollama_gen
                    failing_ctx = "\n".join(
                        f"- [{r.get('platform', '')}] {r['name']} ({r['severity']}): {r['open_count']} open finding(s)"
                        for r in failing[:5]
                    ) or "None — all controls passing."
                    prompt = (
                        f"GRC expert. 3-paragraph executive summary for {fw_name} compliance report.\n"
                        f"Platforms: {', '.join(platforms_list)} | Score: {score}% | Passing: {passed_rules}/{total_rules} | Failing: {failed_rules}\n"
                        f"Top failing:\n{failing_ctx}\n"
                        f"P1: posture and audit readiness. P2: remediation priorities. P3: CIA triad risk. Under 140 words, no bullets."
                    )
                    narrative: str | None = None
                    try:
                        narrative = await asyncio.wait_for(_ollama_gen(prompt), timeout=30.0)
                    except Exception:
                        pass

                    report = DbReport(
                        platform=target_platform,
                        framework=framework,
                        score=score,
                        total_rules=total_rules,
                        passed_rules=passed_rules,
                        failed_rules=failed_rules,
                        ai_narrative=narrative,
                    )
                    db3.add(report)
                    db3.commit()
                    log.info("bg_post_sync: report generated platform=%s framework=%s score=%d", target_platform, framework, score)
                finally:
                    db3.close()
            except Exception as exc:
                log.warning("bg_post_sync: report failed platform=%s framework=%s: %s", target_platform, framework, exc)

    log.info("bg_post_sync: complete platform=%s", platform)


# ── Schedule ──────────────────────────────────────────────────────────────────

@router.patch(
    "/{connector_id}/schedule",
    response_model=ConnectorResponse,
    responses={404: {"description": "Connector not found"}},
)
def set_connector_schedule(
    connector_id: str,
    payload: ConnectorScheduleRequest,
    db: DB,
) -> Connector:
    """Set or clear the auto-sync interval for a connector."""
    obj = _get_connector_or_404(connector_id, db)
    obj.sync_interval_minutes = payload.sync_interval_minutes
    db.commit()
    db.refresh(obj)
    log.info(
        "connector_schedule_updated",
        extra={"id": obj.id, "interval": payload.sync_interval_minutes},
    )
    return obj


# ── Internal helpers ──────────────────────────────────────────────────────────

def _update_connector_health(
    connector: Connector,
    ok: bool,
    error: str | None,
) -> None:
    """Stamp connection health onto the connector row (no commit — caller commits)."""
    connector.connection_ok = ok
    connector.last_sync_at = datetime.now(timezone.utc)
    connector.last_sync_error = error


def _fetch_audit_logs(connector: Any, platform_name: str) -> list[dict]:
    """
    Fetch audit/activity log entries from the connector if supported.
    Returns a list of normalized dicts with keys: actor, action, resource, timestamp.
    """
    if platform_name == "github" and hasattr(connector, "fetch_audit_log"):
        return connector.fetch_audit_log()
    if platform_name == "entraid" and hasattr(connector, "fetch_audit_log"):
        return connector.fetch_audit_log()
    return []


def _build_connector(platform_name: str, credentials: dict, config: dict) -> tuple[Any, str]:
    """Instantiate the right connector class. Returns (connector, neo4j_org_id)."""
    if platform_name == "github":
        from connectors.github_connector import GitHubConnector
        org = (config.get("org") or credentials.get("org", "")).strip()
        return GitHubConnector(credentials=credentials, config=config), org
    if platform_name == "jira":
        from connectors.jira_connector import JiraConnector
        return JiraConnector(credentials=credentials, config=config), config.get("domain", "")
    if platform_name == "salesforce":
        from connectors.salesforce_connector import SalesforceConnector
        return SalesforceConnector(credentials=credentials, config=config), config.get("instance", "")
    if platform_name == "entraid":
        from connectors.entraid_connector import EntraIDConnector
        return EntraIDConnector(credentials=credentials, config=config), config.get("tenant_id", credentials.get("tenant_id", ""))
    raise HTTPException(status_code=400, detail=f"Unknown platform: {platform_name}")


def _persist_entities(db: Session, entities: list[dict]) -> None:
    """Upsert normalized entities into PostgreSQL."""
    from database.models import NormalizedEntity
    for entity_data in entities:
        existing = (
            db.query(NormalizedEntity)
            .filter_by(
                entity_type=entity_data.get("entity_type"),
                platform=entity_data.get("platform"),
                platform_id=str(entity_data.get("platform_id", "")),
            )
            .first()
        )
        if existing:
            existing.data_json = entity_data
            existing.email = entity_data.get("email")
        else:
            db.add(NormalizedEntity(
                entity_type=entity_data.get("entity_type", ""),
                platform=entity_data.get("platform", ""),
                platform_id=str(entity_data.get("platform_id", "")),
                email=entity_data.get("email"),
                data_json=entity_data,
            ))
    db.flush()


def _sync_neo4j(entities: list[dict], neo4j_org_id: str, platform_name: str, progress: Any) -> None:
    """Write entities to Neo4j. Errors are recorded on progress, not re-raised."""
    from core.graph_manager import GraphManager
    gm = GraphManager()
    try:
        gm.create_constraints()
        gm.import_entities(entities, org_id=neo4j_org_id)
        if platform_name == "entraid":
            count = gm.create_federated_identities_by_email()
            log.info("federated_identities", extra={"count": count})
    except Exception as neo_exc:
        progress.record_error("neo4j", str(neo_exc))
    finally:
        gm.close()


def _persist_audit_logs(connector: Any, platform_name: str, connector_id: str, db: Session, progress: Any) -> None:
    """Fetch and persist activity/audit log entries. Errors are recorded on progress."""
    from database.models import ActivityLog
    try:
        entries = _fetch_audit_logs(connector, platform_name)
        for entry in entries:
            db.add(ActivityLog(
                connector_id=connector_id,
                platform=platform_name,
                actor=entry.get("actor"),
                action=entry.get("action", ""),
                resource=entry.get("resource"),
                timestamp=entry.get("timestamp") or datetime.now(timezone.utc),
                raw_json=entry,
            ))
        if entries:
            db.flush()
    except Exception as audit_exc:
        log.warning("audit_log_fetch_error", extra={"error": str(audit_exc)})
        progress.record_error("audit_logs", str(audit_exc))


