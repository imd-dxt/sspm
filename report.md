# SaaS Security Posture Management (SSPM) Platform
## Final Year Project Report

---

## 1. Project Overview

### 1.1 Title
**Design and Implementation of a SaaS Security Posture Management (SSPM) Platform**

### 1.2 Abstract
Modern enterprises rely on dozens of Software-as-a-Service (SaaS) platforms — GitHub, Jira, Salesforce, Microsoft Entra ID — each with its own permission model, audit mechanisms, and security controls. Managing security posture across this fragmented landscape manually is error-prone and slow. This project designs and implements an SSPM platform that automatically discovers, evaluates, and reports security misconfigurations across multiple SaaS platforms through a unified dashboard.

The platform integrates with four major SaaS providers, applies CIS Benchmark and custom detection rules, correlates cross-platform identities, and optionally uses a large language model (LLM) to enrich findings with contextual severity assessments and remediation guidance.

### 1.3 Objectives
1. Build automated connectors for GitHub, Jira, Salesforce, and Microsoft Entra ID
2. Implement a graph-based identity model using Neo4j for cross-platform correlation
3. Design a rule-based detection engine supporting both Cypher and SQL queries
4. Develop a real-time React dashboard for posture monitoring, finding management, and identity analysis
5. Integrate LLM-based analysis (DeepSeek) for enhanced finding context
6. Apply CIS Benchmark standards as the security baseline

---

## 2. Background & Motivation

### 2.1 The SaaS Security Challenge
Organizations using 50+ SaaS tools face a fragmented security landscape. Each platform has unique:
- Identity management (OAuth, SAML, local accounts)
- Role and permission models (RBAC, ABAC)
- Security controls (MFA enforcement, branch protection, session policies)
- Audit and logging mechanisms

Manual audits are time-consuming, inconsistent, and do not scale. SSPM automates this by continuously monitoring configurations.

### 2.2 Industry Context
- Gartner identifies SSPM as a critical emerging security category
- CIS (Center for Internet Security) publishes platform-specific benchmarks
- MITRE ATT&CK and OWASP frameworks provide threat context

### 2.3 Problem Statement
No open-source, multi-platform SSPM tool exists that:
- Integrates with GitHub, Jira, Salesforce, and Entra ID simultaneously
- Builds a unified identity graph across platforms
- Applies CIS benchmarks programmatically
- Provides LLM-enhanced finding analysis

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        React Frontend (Vite)                     │
│   Dashboard | Connectors | Findings | Identities | Rules        │
└───────────────────────────┬─────────────────────────────────────┘
                             │ REST API (JSON)
┌───────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Backend (Python 3.11)                  │
│  /api/v1/connectors  /findings  /rules  /identities  /apps      │
└────┬─────────────────┬──────────────────────┬───────────────────┘
     │                 │                      │
┌────▼────┐     ┌──────▼──────┐      ┌────────▼────────┐
│PostgreSQL│     │    Neo4j    │      │     Redis       │
│Findings  │     │Identity     │      │(future cache)   │
│Rules     │     │Graph        │      └─────────────────┘
│Connectors│     │(Cypher rules)│
└─────────┘     └─────────────┘
     ▲
┌────┴────────────────────────────────────────────────────┐
│                  SaaS Connector Layer                    │
│  GitHub | Jira | Salesforce | Entra ID                  │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Component Breakdown

#### Backend (FastAPI)
- **Connector layer**: Platform-specific adapters implementing a common `BaseConnector` interface
- **Data normalization**: Entities (users, resources, permissions) mapped to a unified `NormalizedEntity` schema
- **Rules engine**: Reads active rules from PostgreSQL, executes detection queries against Neo4j/PostgreSQL, upserts findings with deduplication
- **LLM judge**: Optional DeepSeek integration for severity reassessment and remediation suggestions
- **Auto-sync scheduler**: APScheduler checks `sync_interval_minutes` per connector and triggers sync

#### Graph Database (Neo4j)
- Node types: `User`, `Group`, `Resource`, `Org`, `Application`, `Workflow`
- Relationships: `MEMBER_OF`, `HAS_ROLE`, `BELONGS_TO`, `PART_OF`, `FEDERATED_IDENTITY`
- Detection rules are Cypher queries matched against the graph
- `FEDERATED_IDENTITY` edges correlate the same person across multiple platforms by email

#### Relational Database (PostgreSQL)
- Authoritative store for `connectors`, `scan_runs`, `normalized_entities`, `rules`, `findings`
- Finding deduplication key: `(rule_id, resource_identifier, connector_id)`
- Alembic for schema migrations

#### Frontend (React + TypeScript)
- TanStack Query v5 for server-state management with automatic refetch intervals
- Recharts for charts (posture score, severity breakdown, findings trend)
- ForceGraph: custom force-directed graph using imperative SVG DOM manipulation (no D3 dependency)
- Dark/light theme via CSS custom properties

---

## 4. Implementation

### 4.1 SaaS Connectors

Each connector implements:
```python
class BaseConnector(ABC):
    @abstractmethod
    def test_connection(self) -> dict[str, Any]: ...
    
    @abstractmethod  
    def sync(self) -> SyncProgress: ...
```

**Rate limiting**: `TokenBucket` + `tenacity` retry with exponential backoff.

| Platform | Auth Method | Key Data Collected | Rate Limit |
|----------|-------------|-------------------|------------|
| GitHub | Personal Access Token | Members, teams, repos, branch protection, 2FA | 5000 req/hr |
| Jira | API Token (email + token) | Users, groups, projects, roles, apps | 120 req/min |
| Salesforce | OAuth2 Username-Password | Users, profiles, connected apps, org settings | ~4 req/s |
| Entra ID | OAuth2 Client Credentials | Users (MFA), groups, roles, CA policies, apps | 10 req/s |

### 4.2 Data Normalization
All platform-specific data is normalized to:
```python
NormalizedEntity(
    entity_type: "user" | "resource" | "permission" | "group" | "application",
    platform: str,           # e.g. "github"
    platform_id: str,        # platform's native ID
    email: Optional[str],    # for cross-platform correlation
    data_json: dict          # flexible platform-specific metadata
)
```

### 4.3 Detection Engine

#### Rule Schema
```yaml
- id: CIS-GH-1.1.3
  name: "Branch protection requires code review"
  platform: github
  severity: high
  category: access_control
  cis_control: "1.1.3"
  detection_query: |
    MATCH (r:Resource {platform: 'github', resource_type: 'repository'})
    WHERE NOT (r)-[:HAS_ROLE {role: 'require_pull_request_reviews'}]->()
    RETURN r.uid AS resource_id, r.name AS resource_name
  query_type: cypher
  remediation: "Enable branch protection with required reviewers..."
  compliance_mapping: ["CIS GitHub v1.2.0", "SOC 2 CC6.6"]
```

#### Deduplication
Finding upsert logic:
1. Query: `(rule_id, resource_identifier, connector_id)` → existing finding
2. If `connector_id` is NULL in DB (legacy): backfill and update
3. If found: update `last_detected`, keep status
4. If not found: create new finding with `status=open`, `first_detected=now`

### 4.4 Identity Graph & Cross-Platform Correlation

Neo4j graph enables:
- Path queries: "Which users have admin access to production repos?"
- Cross-platform: user on GitHub + Jira + Entra ID linked via `FEDERATED_IDENTITY`
- Visualization: ForceGraph component renders the user→resource bipartite graph

### 4.5 LLM Judge (DeepSeek)
For each finding, the LLM receives:
- Finding description + evidence
- Rule rationale + remediation
- Returns: `{ llm_severity, llm_severity_reasoning, llm_exploitability, llm_remediation, llm_confidence }`

This augments the rule-based severity with context-aware analysis.

### 4.6 ForceGraph Visualization
A custom force-directed graph implemented without D3:
- **Physics**: repulsion (O(n²)), spring attraction along edges, centering force, velocity damping
- **Rendering**: SVG DOM manipulation in `requestAnimationFrame` loop (60 fps, no React re-renders)
- **Interaction**: node drag (pins node, physics continues), scroll zoom, background pan, hover tooltips
- **Tooltips**: user node shows admin status, finding count, resources; resource node shows user count, roles

---

## 5. Security Design

### 5.1 Credential Storage
Connector credentials are encrypted using **Fernet symmetric encryption** (AES-128-CBC + HMAC) before storing in PostgreSQL. The encryption key is stored in environment variables, not in the database.

### 5.2 API Security
- CORS configured (tighten `allow_origins` for production)
- HTTP request logging with unique `X-Request-ID`
- All exceptions caught and returned as structured JSON (no stack traces in production)

### 5.3 Finding Lifecycle
Findings follow a managed lifecycle with mandatory justification for dismissals:
```
open → resolved | false_positive (requires justification) | accepted_risk (requires justification)
```

---

## 6. Dashboard & UI Features

### 6.1 Dashboard
- **Posture Score**: Weighted severity score (critical×4 + high×3 + medium×2 + low×1), normalized 0–100
- **KPI Strip**: Total open findings, critical count, active connectors, platforms
- **Severity radial chart**: ConnectorsRadial half-circle gauge
- **Open Findings Trend**: AreaChart of open findings per connector per sync
- **Recent findings table**: Latest 5 open findings with severity badges

### 6.2 Findings Page
- Filterable table: by severity, status, platform, connector, keyword search
- **Severity donut chart**: current open findings by severity
- **Status trend chart**: findings over time by status (weekly aggregation)
- **Finding drawer**: full detail with evidence, LLM analysis, status lifecycle controls

### 6.3 SaaS Identities Page
- Platform picker with user/resource counts
- Stats strip: total users, admins, users at risk, resources
- **Identity charts**: admins/users donut, users at risk gauge, resources at risk bar
- Users table: expandable rows with resource access chips
- Findings by resource table
- **ForceGraph**: interactive force-directed access map

### 6.4 Third-Party Apps
Inventory of OAuth apps, GitHub Apps, Entra service principals with finding counts.

### 6.5 Connectors
- Add/test/sync/delete connectors
- Per-connector status, last sync time, coverage progress bar
- Schedule auto-sync with interval selector

---

## 7. Rules Coverage

| Platform | Standard | Rules | Auto-detectable |
|----------|----------|-------|----------------|
| GitHub | CIS GitHub Benchmark v1.2.0 | ~25 | ~20 |
| Jira | Internal security baseline | ~40 | ~25 |
| Salesforce | CSA SaaS Governance | ~45 | ~30 |
| Entra ID | Microsoft Security Baseline | ~20 | ~18 |

Detection categories: Authentication, Access Control, Branch Protection, Code Security, Third-party Apps, Session Management, Data Protection, Monitoring, Compliance.

---

## 8. Technical Challenges & Solutions

| Challenge | Solution |
|-----------|---------|
| Different auth models per platform | Abstract `BaseConnector` with platform-specific subclasses |
| Rate limiting at scale | `TokenBucket` rate limiter + `tenacity` exponential backoff |
| Duplicate findings on re-scan | Two-step dedup: exact match first, NULL connector_id fallback |
| Cross-platform identity correlation | Email-based exact matching → `FEDERATED_IDENTITY` Neo4j edges |
| Real-time graph visualization performance | Direct SVG DOM manipulation (bypasses React reconciler) |
| Credential security | Fernet AES encryption at rest |
| Schema migration without downtime | Alembic versioned migrations |

---

## 9. Testing

```
tests/
├── test_core/
│   └── test_rules_engine.py    # Rule execution + deduplication logic
└── test_connectors/
    └── test_github_connector.py # Connector integration tests (mocked HTTP)
```

Run: `pytest --cov=. --cov-report=term-missing`

---

## 10. Deployment

### Docker Compose Stack
```yaml
services:
  postgres:   image: postgres:15, port: 5432
  neo4j:      image: neo4j:5,     ports: 7474, 7687
  redis:      image: redis:7,     port: 6379
```

### Environment Variables (`.env`)
```
POSTGRES_URL=postgresql://sspm:sspm_pass@localhost:5432/sspm
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=sspm_neo4j_pass
REDIS_URL=redis://localhost:6379
ENCRYPTION_KEY=<fernet-key>
DEEPSEEK_API_KEY=<optional>
```

### Startup Sequence
```bash
cd docker && docker-compose up -d     # start databases
alembic upgrade head                   # run migrations
python -m scripts.load_rules           # seed detection rules (all platforms)
uvicorn api.main:app --reload          # start API
cd frontend && npm run dev             # start UI
```

---

## 11. Results & Evaluation

### 11.1 Functional Achievements
- ✅ 4 SaaS platform connectors fully operational
- ✅ 130+ detection rules across platforms
- ✅ Real-time dashboard with posture scoring
- ✅ Cross-platform identity correlation
- ✅ LLM-enhanced finding analysis
- ✅ Interactive force-directed identity graph
- ✅ Full finding lifecycle management

### 11.2 Performance Observations
- GitHub sync (100 users, 50 repos): ~8–12 seconds
- Salesforce sync (500 users): ~15–20 seconds
- Rules engine (50 rules, small org): ~2–3 seconds
- Frontend loads findings table (200 rows): <200ms render

### 11.3 Limitations
- LLM analysis requires paid DeepSeek API key
- Some Jira/Salesforce rules require elevated admin API access
- Neo4j required in addition to PostgreSQL (operational complexity)
- No authentication/authorization on the API (single-tenant assumption)
- Auto-sync uses APScheduler in-process (not production-grade; Celery/ARQ recommended)

---

## 12. Future Work

1. **Authentication**: Add JWT/OAuth2 multi-tenant support
2. **More platforms**: Slack, Google Workspace, Okta, AWS IAM
3. **Remediation automation**: Auto-fix low-risk misconfigs via platform APIs
4. **Alerting**: Email/Slack notifications for new critical findings
5. **Compliance reports**: PDF export for SOC 2, ISO 27001 audits
6. **Production task queue**: Replace APScheduler with Celery + Redis
7. **ML anomaly detection**: Behavioral analysis on access patterns

---

## 13. References

1. CIS GitHub Benchmark v1.2.0 — https://www.cisecurity.org/benchmark/github
2. CSA SaaS Governance Best Practices — https://cloudsecurityalliance.org
3. Microsoft Security Baseline for Entra ID — https://docs.microsoft.com/security
4. OWASP Top 10 — https://owasp.org/Top10
5. MITRE ATT&CK for Enterprise — https://attack.mitre.org
6. Neo4j Graph Data Science — https://neo4j.com/docs
7. FastAPI Documentation — https://fastapi.tiangolo.com
8. Recharts Documentation — https://recharts.org

---

*Project developed as a final-year engineering project. All SaaS API integrations use read-only scopes. No production systems were modified during testing.*
