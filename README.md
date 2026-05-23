# SSPM Platform

SaaS Security Posture Management platform. Detects misconfigurations across SaaS tools against CIS benchmarks, starting with GitHub.

## Architecture

```
GitHub API  ──►  GitHubConnector  ──►  NormalizedEntities
                                              │
                               ┌──────────────┼──────────────┐
                               ▼              ▼              ▼
                          PostgreSQL        Neo4j        RulesEngine
                         (audit trail)  (access graph)  (findings)
                               └──────────────┴──────────────┘
                                              │
                                        FastAPI REST
```

- **Connector Layer** — platform-specific adapters that normalize data to a common schema
- **Core Layer** — graph storage, identity correlation, DB-driven detection rules
- **API Layer** — REST endpoints for connectors, rules, and findings

---

## Quick Start

### 1. Prerequisites

- Docker Desktop
- Python 3.11+

### 2. Start infrastructure

```bash
cd docker
docker-compose up -d postgres neo4j redis
```

Wait ~15 seconds, then verify:
```bash
docker-compose ps
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
```
GITHUB_TOKEN=ghp_your_token_here
GITHUB_ORG=your-org-name
ENCRYPTION_KEY=<generate below>
```

Generate an encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run database migrations

```bash
alembic upgrade head
```

### 6. Load detection rules

```bash
# GitHub CIS rules
python -m scripts.load_rules

# Jira security rules
python -m scripts.load_jira_rules
```

### 7. Start the API

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

---

## Full Detection Pipeline

### Register the connector

```bash
curl -X POST http://localhost:8000/api/v1/connectors/ \
  -H "Content-Type: application/json" \
  -d '{
    "platform_name": "github",
    "display_name": "My GitHub Org",
    "credentials": {"token": "ghp_your_token_here"},
    "config": {"org": "your-org-name"}
  }'
```

Save the returned `id` as `CONNECTOR_ID`.

### Test the connection

```bash
curl http://localhost:8000/api/v1/connectors/$CONNECTOR_ID/test
```

### Sync GitHub data

```bash
curl -X POST http://localhost:8000/api/v1/connectors/$CONNECTOR_ID/sync
```

Fetches all users, teams, repositories, and permissions from GitHub → stores in PostgreSQL and Neo4j → automatically runs all detection rules.

### Run detection manually

```bash
# All platforms
python -m scripts.run_detection

# GitHub only
python -m scripts.run_detection --platform github

# Single rule
python -m scripts.run_detection --rule CIS-GH-1.1.3

# JSON output
python -m scripts.run_detection --json
```

### View findings

```bash
# Summary by severity and status
curl http://localhost:8000/api/v1/findings/summary

# All open findings
curl "http://localhost:8000/api/v1/findings/"

# Filter by severity / platform / rule
curl "http://localhost:8000/api/v1/findings/?severity=critical"
curl "http://localhost:8000/api/v1/findings/?platform=github&severity=high"

# Single finding with evidence
curl http://localhost:8000/api/v1/findings/1

# Update status
curl -X PUT "http://localhost:8000/api/v1/findings/1/status?status=resolved"

# Dismiss as false positive
curl -X POST "http://localhost:8000/api/v1/findings/1/dismiss?reason=false_positive"
```

---

## Jira Connector

### Prerequisites

1. Jira Cloud instance (`yourcompany.atlassian.net`)
2. Jira account with **admin** permissions
3. API token — generate at https://id.atlassian.com/manage-profile/security/api-tokens

### Register the Jira connector

```bash
curl -X POST http://localhost:8000/api/v1/connectors/ \
  -H "Content-Type: application/json" \
  -d '{
    "platform_name": "jira",
    "display_name": "My Jira Workspace",
    "credentials": {
      "email": "admin@yourcompany.com",
      "api_token": "YOUR_API_TOKEN"
    },
    "config": {"domain": "yourcompany.atlassian.net"}
  }'
```

### Test the connection

```bash
curl http://localhost:8000/api/v1/connectors/$CONNECTOR_ID/test
```

### Sync Jira data

```bash
curl -X POST http://localhost:8000/api/v1/connectors/$CONNECTOR_ID/sync
```

Fetches users, groups, projects, project role assignments, and installed apps → stores in PostgreSQL and Neo4j → runs all Jira detection rules.

### Load Jira rules

```bash
python -m scripts.load_jira_rules          # load from jira_security_rules.yaml
python -m scripts.load_jira_rules --dry-run  # preview without writing
```

### Run Jira detection

```bash
python -m scripts.run_detection --platform jira
python -m scripts.run_detection --platform jira --json
```

### View Jira findings

```bash
curl "http://localhost:8000/api/v1/findings/?platform=jira"
curl "http://localhost:8000/api/v1/findings/?platform=jira&severity=high"
```

### Jira API limitations

The following rule categories cannot be fully automated with the Jira Cloud REST API and require the **Atlassian Admin API** (planned Phase 3):

| Rules | Missing data | Workaround |
|-------|-------------|------------|
| JIRA-AUTH-001/003/004/005 | 2FA enforcement, SSO, domain verification, password policy | Manual review at admin.atlassian.com → Security |
| JIRA-AUTH-002 | Per-user 2FA status | Manual review |
| JIRA-ACCESS-004/006/007 | Public signup, Browse Users permission, last login date | Manual review |
| JIRA-API-001/002 | Password-based API access, token expiration | Manual review |
| JIRA-AUDIT-001/002 | Audit log retention/forwarding settings | Manual review |
| JIRA-DATA-001/002 | Encryption settings, issue content scanning | Manual review |
| JIRA-CONFIG-002/003 | CAPTCHA, SMTP TLS settings | Manual review |
| JIRA-MOBILE-001 | Mobile device management policy | Manual review (requires Atlassian Guard) |

Rules that fire automatically with the REST API: `JIRA-ACCESS-001/002/003/005`, `JIRA-PROJECT-001/002/003`, `JIRA-APP-001/002/003`, `JIRA-API-003`, `JIRA-CONFIG-001`, `JIRA-WORKFLOW-001`.

---

## Salesforce Connector

### Prerequisites

1. Salesforce org (Production or Sandbox)
2. **Connected App** with OAuth 2.0 Username-Password Flow enabled:
   - Setup → Apps → App Manager → New Connected App
   - Enable OAuth Settings → add `api` scope
   - Note the **Consumer Key** (client_id) and **Consumer Secret** (client_secret)
3. Admin user API token (username + password + security token)
4. Security token — from Setup → My Personal Information → Reset My Security Token

### Register the Salesforce connector

```bash
curl -X POST http://localhost:8000/api/v1/connectors/ `
  -H "Content-Type: application/json" `
  -d '{
    "platform_name": "salesforce",
    "display_name": "My Salesforce Org",
    "credentials": {
      "client_id": "3MVG9...",
      "client_secret": "YOUR_SECRET",
      "username": "admin@yourcompany.com",
      "password": "YourPassword",
      "security_token": "YOUR_TOKEN"
    },
    "config": {"instance": "yourcompany.my.salesforce.com"}
  }'
```

### Test the connection

```bash
curl http://localhost:8000/api/v1/connectors/$CONNECTOR_ID/test
```

### Sync Salesforce data

```bash
curl -X POST http://localhost:8000/api/v1/connectors/$CONNECTOR_ID/sync
```

Fetches users, profiles, connected apps, and org metadata → stores in PostgreSQL and Neo4j → runs all Salesforce detection rules.

### Load Salesforce rules

```bash
python -m scripts.load_salesforce_rules          # load from salesforce_security_rules.yaml
python -m scripts.load_salesforce_rules --dry-run  # preview without writing
```

### Run Salesforce detection

```bash
python -m scripts.run_detection --platform salesforce
python -m scripts.run_detection --platform salesforce --json
```

### Salesforce API limitations

The following rules cannot be fully automated with the Salesforce REST API v59.0 and require the **Metadata API**, **Tooling API**, or additional licenses:

| Rules | Missing data | Workaround |
|-------|-------------|------------|
| SF-AUTH-001 | MFA enforcement status | Manual review at Setup → Identity → MFA |
| SF-AUTH-002 | Password policy settings | Manual review at Setup → Security → Password Policies |
| SF-AUTH-003 | SSO configuration | Manual review at Setup → Identity → SSO Settings |
| SF-USER-002 | Sandbox user sanitization | Manual review after sandbox refresh |
| SF-USER-003 | SCIM/Identity Connect status | Manual review |
| SF-AUTHZ-005 | SOD conflict matrix | Manual review |
| SF-EMERG-002 | Emergency login events | Requires Event Monitoring license |
| SF-SESS-001/002 | Session timeout, Login-As events | Manual review / Event Monitoring |
| SF-APP-001 | Health Check score | Manual review at Setup → Security → Security Health Check |
| SF-APP-002/003/004 | Critical updates, Apex analysis, AppExchange packages | Manual review |
| SF-DATA-001/002/003 | Shield encryption, field history, sandbox masking | Requires Salesforce Shield |
| SF-DATA-004 | Event Monitoring enabled | Manual review + license required |
| SF-NET-001/002 | HSTS, Apex HTTPS callouts | Manual review |
| SF-INT-002 | Integration user password age | Metadata API required |
| SF-CHG-001 | Prod changes without sandbox test | Manual review |
| SF-MON-001/002/03 | SIEM, Login Forensics, Transaction Security | Tooling API / Manual |
| SF-COMP-001/002 | Data classification, OWD sharing | Metadata API required |
| SF-LAND-002 | Cross-env interfaces | Manual review |

Rules that fire automatically with the REST API: `SF-AUTH-004`, `SF-USER-001`, `SF-AUTHZ-001/002/003/004`, `SF-EMERG-001`, `SF-INT-001/003`.

---

## Detection Rules

Rules are stored in PostgreSQL and executed by the universal rules engine. Each platform's rules live in a YAML file.

**GitHub** — 25 CIS GitHub Benchmark v1.2.0 rules (`github_cis_rules.yaml`)

| Family | Controls |
|--------|----------|
| Branch Protection | PR reviews, stale review dismissal, code owner review, signed commits, status checks |
| Identity & Access | MFA enforcement, admin minimization, OAuth app restrictions, external collaborators |
| Code Scanning | Secret scanning, CodeQL, Dependabot, security policy, CODEOWNERS |
| Third-party | Webhook secrets, inactive repos |

**Jira** — 40 security rules (`jira_security_rules.yaml`)

| Family | Rules | Auto-detected |
|--------|-------|---------------|
| Authentication | MFA, SSO, domain verification, password policy | Partial (REST API limits) |
| Access Control | Excessive admins, over-privileged users, public signup, external admin | Yes |
| Project Config | Missing roles, single admin, no issue security scheme | Yes |
| Third-party Apps | Excessive permissions, unused apps, OAuth approval | Yes |
| API Security | Service accounts, token expiry | Partial |
| Audit & Monitoring | Log retention, SIEM forwarding | Requires Admin API |
| Workflow | Transition restrictions | Yes |

**Salesforce** — 45 security rules (`salesforce_security_rules.yaml`)

| Family | Rules | Auto-detected |
|--------|-------|---------------|
| Authentication | MFA, password policy, SSO, login IP restrictions | Partial (IP restrictions: Yes) |
| User Management | Inactive accounts, sandbox users, identity management | Partial (inactive: Yes) |
| Authorization | Excessive admins, ViewAllData, ModifyAllData, AuthorApex, SOD | Yes (permissions) |
| Emergency Access | Break-glass accounts, login monitoring | Partial (account detection: Yes) |
| Session Security | Timeout, Login-As monitoring | Requires Metadata API |
| Application Security | Health Check, critical updates, Apex code, AppExchange | Partial |
| Data Protection | Shield encryption, field history, sandbox masking, Event Monitoring | Requires Shield |
| Network Security | HSTS, Apex HTTPS callouts | Manual review |
| Integration Security | Connected app IP restrictions, scope analysis | Yes |
| Change Management | Sandbox testing, version control | Partial |
| Monitoring | Audit trail SIEM, login forensics, transaction security | Partial |
| Compliance | Data classification, sharing model | Requires Metadata API |
| Landscape | My Domain, cross-env interfaces | Partial |

### Manage rules via API

```bash
# List all active rules
curl http://localhost:8000/api/v1/rules/

# Filter by platform or severity
curl "http://localhost:8000/api/v1/rules/?platform=github&severity=critical"

# Get rule details (includes Cypher query)
curl http://localhost:8000/api/v1/rules/CIS-GH-1.1.3

# Run all rules now
curl -X POST http://localhost:8000/api/v1/rules/run

# Run a single rule
curl -X POST http://localhost:8000/api/v1/rules/CIS-GH-1.1.3/run
```

### Reload rules from YAML

```bash
# Preview without writing
python -m scripts.load_rules --dry-run

# Load / update rules in DB
python -m scripts.load_rules

# Use a different YAML file
python -m scripts.load_rules --yaml path/to/custom_rules.yaml
```

---

## Neo4j Browser

Open http://localhost:7474  
Login: `neo4j` / `sspm_neo4j_pass`

### Useful Cypher queries

```cypher
// All nodes
MATCH (n) RETURN n LIMIT 50

// Users without MFA
MATCH (u:User {platform: 'github'})
WHERE u.two_factor = false OR u.two_factor IS NULL
RETURN u.username, u.github_role ORDER BY u.github_role DESC

// Unprotected public repos
MATCH (r:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE r.branch_protected = false AND r.visibility = 'public'
RETURN r.name, r.visibility

// Who has admin access?
MATCH (u:User)-[r:HAS_ROLE {role: 'admin'}]->(res:Resource)
RETURN u.username, res.name ORDER BY u.username

// Repos missing secret scanning
MATCH (r:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE r.secret_scanning_enabled = false OR r.secret_scanning_enabled IS NULL
RETURN r.name, r.visibility

// Full access graph (small orgs only)
MATCH p=(u:User)-[:HAS_ROLE|MEMBER_OF*1..2]->(n)
RETURN p LIMIT 100
```

---

## Running Tests

```bash
pytest
```

With coverage:
```bash
pytest --cov=. --cov-report=term-missing
```

---

## Docker Compose (full stack)

```bash
cd docker
docker-compose up --build
```

Starts PostgreSQL, Neo4j, Redis, runs `alembic upgrade head`, and starts the API on port 8000.

---

## Project Structure

```
sspm/
├── connectors/              # SaaS platform adapters
│   ├── base_connector.py
│   ├── github_connector.py
│   ├── jira_connector.py
│   └── salesforce_connector.py
├── core/                    # Analysis layer
│   ├── graph_manager.py         # Neo4j operations
│   ├── rules_engine.py          # DB-driven detection engine
│   ├── rules_loader.py          # YAML → PostgreSQL rule loader
│   └── identity_correlator.py
├── database/                # PostgreSQL layer
│   ├── models.py                # Rule, Finding, Connector, ScanRun, NormalizedEntity
│   ├── session.py
│   └── migrations/
│       └── versions/
│           ├── 0001_initial_schema.py
│           └── 0002_rules_and_findings.py
├── api/                     # FastAPI REST server
│   ├── main.py
│   └── routes/
│       ├── connectors.py        # /connectors
│       ├── rules.py             # /rules
│       └── findings.py          # /findings
├── scripts/                 # CLI utilities
│   ├── load_rules.py            # Load GitHub rules into DB
│   ├── load_jira_rules.py       # Load Jira rules into DB
│   ├── load_salesforce_rules.py # Load Salesforce rules into DB
│   └── run_detection.py         # Run detection rules (--platform github|jira|salesforce)
├── config/                  # Settings and logging
├── utils/                   # Shared utilities
│   ├── http_client.py           # Rate-limited HTTP with retry
│   ├── crypto.py                # Fernet encryption
│   └── validators.py
├── tests/
├── docker/
│   ├── docker-compose.yml
│   └── Dockerfile
├── github_cis_rules.yaml         # CIS GitHub Benchmark v1.2.0 rules (25 rules)
├── jira_security_rules.yaml      # Jira security best practices (40 rules)
└── salesforce_security_rules.yaml # Salesforce CSA security rules (45 rules)
```

---

## GitHub Token Scopes Required

| Scope | Purpose |
|-------|---------|
| `read:org` | Org members, teams, MFA status |
| `repo` | Repository metadata, branch protection, security features |
| `read:user` | User profiles |
| `admin:org` | MFA enforcement status (requires org owner) |

---

## LLM Architecture

The SSPM platform uses a **privacy-first hybrid LLM architecture** that routes AI tasks to the appropriate model based on data sensitivity.

### LLM Router (`core/llm_router.py`)

The `LLMRouter` class orchestrates two LLM backends:

| Provider | Location | Use cases | Data sent |
|----------|----------|-----------|-----------|
| **Ollama** (local) | Your server | Remediation steps, Q&A, finding explanations | Raw finding data — never leaves your infrastructure |
| **DeepSeek** (cloud) | api.deepseek.com | Executive summaries, exploitation scenarios, trend narratives | Anonymised aggregates only |

### Privacy Guarantees

**No sensitive data is ever sent to DeepSeek.** The router enforces this via `sanitise()`, which replaces the following field types with opaque tokens before any cloud API call:

- Usernames, emails, display names
- Tenant IDs, account IDs, client secrets
- Organisation names, domain names, internal URLs
- IP addresses

Token maps are held in memory only for the duration of a single LLM call and are immediately discarded — they are never logged, persisted, or stored in the database.

### Setup

```bash
# Install local LLM
ollama pull llama3.2

# Configure environment
DEEPSEEK_API_KEY=sk-your-key
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
LLM_TIMEOUT_OLLAMA=60
LLM_TIMEOUT_DEEPSEEK=30
```

If neither Ollama nor DeepSeek is configured, the platform continues to work — AI sections in reports display a placeholder message instead of failing.

---

## Roadmap

- [x] Salesforce connector (users, profiles, connected apps, org settings)
- [ ] Okta connector (users, groups, app assignments)
- [ ] Slack connector (workspace users, channel permissions)
- [ ] Identity correlation across platforms (email matching → graph merge)
- [ ] Scheduled syncs (cron / Celery + Redis)
- [ ] Dashboard UI
- [ ] Webhook-based real-time sync
- [ ] GitHub Actions / CI-CD scanning
