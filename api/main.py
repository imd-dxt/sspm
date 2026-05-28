"""
SSPM FastAPI application entry point.

Run with:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""
import time
import uuid
import logging

import structlog
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.logging_config import configure_logging
from config.settings import settings
from api.auth import get_current_user
from api.routes import auth, connectors, findings, rules, scan_runs, third_party_apps, identities, activity_logs, posture, compliance

API_V1 = "/api/v1"

configure_logging(level=settings.log_level, fmt=settings.log_format)
log = structlog.get_logger()


# ── Auto-sync scheduler ───────────────────────────────────────────────────────

def _run_scheduled_syncs() -> None:
    """Called by APScheduler every minute. Triggers syncs for connectors that are due."""
    try:
        from datetime import datetime, timezone, timedelta
        from database.session import SessionLocal
        from database.models import Connector

        db = SessionLocal()
        try:
            due = db.query(Connector).filter(
                Connector.sync_interval_minutes.isnot(None),
                Connector.is_active == True,  # noqa: E712
            ).all()

            for connector in due:
                interval = connector.sync_interval_minutes
                last = connector.last_sync_at
                now = datetime.now(timezone.utc)
                if last is None or (now - last) >= timedelta(minutes=interval):
                    log.info("auto_sync_triggered", extra={"connector_id": connector.id})
                    try:
                        # Reuse the sync logic from the connectors route
                        from api.routes.connectors import trigger_sync
                        trigger_sync(connector.id, db)
                    except Exception as exc:
                        log.warning("auto_sync_failed", extra={"connector_id": connector.id, "error": str(exc)})
        finally:
            db.close()
    except Exception as exc:
        log.warning("scheduler_error", extra={"error": str(exc)})


def _seed_rules() -> None:
    """Load all rule YAML files into the DB on startup (idempotent upsert)."""
    import os
    from pathlib import Path
    from database.session import SessionLocal
    from core.rules_loader import RulesLoader

    rules_dir = Path(os.getenv("RULES_DIR", "/app/rules"))
    if not rules_dir.exists():
        log.warning("rules_dir_not_found", rules_dir=str(rules_dir))
        return

    yaml_files = list(rules_dir.glob("*.yaml"))
    if not yaml_files:
        log.warning("no_rule_yaml_files", rules_dir=str(rules_dir))
        return

    db = SessionLocal()
    try:
        loader = RulesLoader(db)
        for yaml_file in sorted(yaml_files):
            try:
                result = loader.load_from_yaml(str(yaml_file))
                log.info("rules_seeded", file=yaml_file.name, **result)
            except Exception as exc:
                log.warning("rules_seed_failed", file=yaml_file.name, error=str(exc))
    finally:
        db.close()


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Seed rules from YAML on every startup (upsert — safe to run repeatedly)
    try:
        _seed_rules()
    except Exception as exc:
        log.warning("rules_seed_error", error=str(exc))

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(_run_scheduled_syncs, "interval", minutes=1, id="auto_sync")
        scheduler.start()
        log.info("scheduler_started")
        application.state.scheduler = scheduler
    except ImportError:
        log.warning("apscheduler_not_installed", extra={"hint": "pip install apscheduler"})
        application.state.scheduler = None

    yield

    scheduler = getattr(application.state, "scheduler", None)
    if scheduler:
        scheduler.shutdown(wait=False)
        log.info("scheduler_stopped")


app = FastAPI(
    lifespan=lifespan,
    title="SSPM Platform",
    description="SaaS Security Posture Management – Phase 1",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next) -> Response:
    request_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)

    log.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

# Auth router is public (no token required for login)
app.include_router(auth.router, prefix=API_V1)

# All other routers require a valid JWT
_auth_dep = [Depends(get_current_user)]
app.include_router(connectors.router, prefix=API_V1, dependencies=_auth_dep)
app.include_router(findings.router, prefix=API_V1, dependencies=_auth_dep)
app.include_router(rules.router, prefix=API_V1, dependencies=_auth_dep)
app.include_router(scan_runs.router, prefix=API_V1, dependencies=_auth_dep)
app.include_router(third_party_apps.router, prefix=API_V1, dependencies=_auth_dep)
app.include_router(identities.router, prefix=API_V1, dependencies=_auth_dep)
app.include_router(activity_logs.router, prefix=API_V1, dependencies=_auth_dep)
app.include_router(posture.router, prefix=API_V1, dependencies=_auth_dep)
app.include_router(compliance.router, prefix=API_V1, dependencies=_auth_dep)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Returns service status. Used by Docker health checks and load balancers."""
    services: dict[str, str] = {}

    # PostgreSQL
    try:
        from database.session import engine
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception as exc:
        services["postgres"] = f"error: {exc}"

    # Neo4j
    try:
        from core.graph_manager import GraphManager
        gm = GraphManager()
        gm._driver.verify_connectivity()
        gm.close()
        services["neo4j"] = "ok"
    except Exception as exc:
        services["neo4j"] = f"error: {exc}"

    # Redis
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.redis_url)
        r.ping()
        services["redis"] = "ok"
    except Exception as exc:
        services["redis"] = f"error: {exc}"

    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"
    return {"status": overall, "version": "0.1.0", "services": services}


# ── Dev entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=settings.api_host, port=settings.api_port, reload=True)
