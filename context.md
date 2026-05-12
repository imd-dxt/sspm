# SSPM Platform — Claude Context

> Paste this file at the start of a new session so Claude understands the project without re-exploring it.

---

## What it is
A **SaaS Security Posture Management (SSPM)** platform built as a final-year engineering project. It continuously scans SaaS platforms for security misconfigurations and presents findings in a React dashboard.

## Tech stack

| Layer | Tech |
|-------|------|
| Backend API | FastAPI 0.111, Python 3.11, uvicorn |
| Relational DB | PostgreSQL 15 + SQLAlchemy 2 + Alembic |
| Graph DB | Neo4j 5 (Cypher queries for detection rules) |
| Cache/Queue | Redis 7 |
| Frontend | React 18 + TypeScript 5 + Vite 5 |
| State / Data | TanStack Query v5 |
| Charts | Recharts 2.12 |
| Icons | Lucide-React |
| Styling | Tailwind CSS 3 + custom CSS vars in `tokens.css` |
| LLM | DeepSeek via LangChain (finding analysis) |

## Project layout
```
sspm/
├── api/
│   ├── main.py               # FastAPI app, CORS, scheduler, health
│   └── routes/
│       ├── connectors.py     # CRUD + sync + test + schedule
│       ├── findings.py       # list/get/status/dismiss/analyze/trend
│       ├── rules.py          # CRUD + run
│       ├── scan_runs.py      # scan history
│       ├── third_party_apps.py
│       └── identities.py     # SaaS Identities module (platforms/summary/users/graph)
├── config/
│   ├── settings.py           # Pydantic BaseSettings from .env
│   └── logging_config.py     # structlog JSON/console
├── connectors/
│   ├── base_connector.py     # ABC + SyncProgress + retry logic
│   ├── github_connector.py   # GitHub org (users/teams/repos/branch-protection)
│   ├── jira_connector.py     # Jira Cloud (users/groups/projects/apps)
│   ├── salesforce_connector.py # Salesforce (users/profiles/connected-apps)
│   └── entraid_connector.py  # Entra ID (users/groups/roles/CA-policies/apps)
├── core/
│   ├── rules_engine.py       # Universal detection → Finding upsert (dedup by rule+resource+connector)
│   ├── graph_manager.py      # Neo4j node/edge ops + federated identity by email
│   ├── rules_loader.py       # YAML → PostgreSQL rule import
│   ├── identity_correlator.py # Cross-platform email-match → FEDERATED_IDENTITY edges
│   └── llm_judge.py          # DeepSeek analysis: severity/exploitability/remediation
├── database/
│   ├── models.py             # Connector, ScanRun, NormalizedEntity, Rule, Finding
│   ├── schemas.py            # Pydantic request/response schemas
│   └── session.py            # SQLAlchemy engine + get_db dependency
├── utils/
│   ├── http_client.py        # RateLimitedSession + TokenBucket
│   └── crypto.py             # Fernet encrypt/decrypt for credentials
├── *_rules.yaml              # Detection rules (github/jira/salesforce/entraid)
├── frontend/src/
│   ├── pages/                # Dashboard, Connectors, Findings, Identities, Rules, ScanRuns, ThirdPartyApps, Settings
│   ├── components/
│   │   ├── layout/           # Sidebar, Topbar, Header, Layout
│   │   ├── findings/         # FindingDrawer, SeverityBadge
│   │   ├── connectors/       # AddConnectorModal, ConnectorCard
│   │   ├── identities/       # ForceGraph (D3-style force simulation)
│   │   └── shared/           # PlatformLogo
│   ├── api/                  # React Query hooks + typed client
│   │   ├── client.ts         # fetch wrapper (get/post/put/patch/del)
│   │   ├── types.ts          # All TS interfaces
│   │   ├── connectors.ts, findings.ts, rules.ts, identities.ts, thirdPartyApps.ts
│   ├── lib/utils.ts           # formatRelative, platformLabel, calcPostureScore, statusLabel
│   └── theme/tokens.css      # CSS custom properties + component classes
```

## Key database models

```python
Connector      id(UUID), platform_name, display_name, credentials_encrypted, config_json,
               connection_ok, last_sync_at, last_sync_error, sync_interval_minutes, is_active

ScanRun        id(UUID), connector_id(FK), status, started_at, completed_at,
               records_fetched, findings_count(open at scan time), errors_json

NormalizedEntity  id, entity_type(user|resource|permission|group|application),
                  platform, platform_id, email, data_json(JSONB)

Rule           id(str e.g."CIS-GH-1.1.3"), name, platform, severity, category,
               detection_query(Cypher/SQL), query_type, description, remediation,
               compliance_mapping, is_active

Finding        id(int), rule_id(FK), connector_id, connector_name, platform,
               resource_type, resource_identifier, severity, category, description,
               evidence(JSONB), status(open|resolved|false_positive|accepted_risk),
               justification, first_detected, last_detected, resolved_at,
               llm_severity, llm_exploitability, llm_remediation, llm_confidence
```

## API base path
All endpoints under `/api/v1/`

## Supported platforms
`github`, `jira`, `salesforce`, `entraid`

## Detection rules
- CIS GitHub Benchmark v1.2.0 (~25 rules)
- Jira security rules (~40)
- Salesforce CSA rules (~45)
- Entra ID security rules

Rules are Cypher (Neo4j) or SQL queries stored in PostgreSQL, loaded from YAML files via `scripts/load_*.py`.

## Styling conventions
- CSS variables in `:root` / `[data-theme="dark"]` (in `tokens.css`)
- Key vars: `--bg`, `--surface`, `--surface-2`, `--text`, `--text-muted`, `--accent`, `--border`
- Severity colors: `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-low`, `--sev-ok`
- Sidebar: `--sidebar-bg` (`#0B0875` light / `#211361` dark), white text
- Component classes: `.card`, `.btn-primary`, `.btn-ghost`, `.input`, `.select`, `.modal`, `.drawer`
- Theme toggle: `document.documentElement.dataset.theme = 'dark'|'light'`

## Notable design decisions
- **Finding dedup**: `(rule_id, resource_identifier, connector_id)` — backfills NULL connector_id from old records on match
- **findings_count on ScanRun**: total *open* findings for that connector at scan completion (not incremental count)
- **Admin detection**: GitHub `metadata.site_admin`, Salesforce `metadata.is_system_admin`, EntraID `metadata.roles`, plus permission-entity role heuristics
- **ForceGraph**: imperative SVG DOM manipulation in rAF loop (no React re-renders per frame), React state only for tooltip
- **Auto-sync**: APScheduler runs `_run_scheduled_syncs` every minute, checks `sync_interval_minutes` per connector
- **LLM Judge**: optional DeepSeek analysis, populates `llm_*` fields, 503 if key not configured
- **Credentials**: Fernet-encrypted at rest in `connectors.credentials_encrypted`

## Run commands
```bash
# Backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Frontend  
cd frontend && npm run dev

# Load rules
python -m scripts.load_rules
python -m scripts.load_jira_rules
python -m scripts.load_salesforce_rules
python -m scripts.load_entraid_rules

# Run detection manually
python -m scripts.run_detection --platform github

# Migrations
alembic upgrade head

# Docker stack (Postgres + Neo4j + Redis)
cd docker && docker-compose up -d
```

## Current feature status
| Feature | Status |
|---------|--------|
| GitHub connector | ✅ Working |
| Jira connector | ✅ Working (some rules require Admin API) |
| Salesforce connector | ✅ Working |
| Entra ID connector | ✅ Working |
| Detection rules engine | ✅ Working |
| LLM finding analysis | ✅ Working (requires DeepSeek key) |
| Cross-platform identity correlation | ✅ Working |
| Auto-sync scheduler | ✅ Working (APScheduler) |
| SaaS Identities module | ✅ Implemented |
| Third-Party Apps module | ✅ Implemented |
| ForceGraph visualization | ✅ Implemented |
| Findings trend chart | ✅ Implemented |
