"""
RulesLoader – parses github_cis_rules.yaml and upserts rules into PostgreSQL.

Corrected Cypher queries are applied on load so they match our actual Neo4j schema:
  - resource_subtype instead of resource_type
  - HAS_ROLE instead of CAN_ACCESS
  - r.role instead of r.access_level
  - Org node instead of Group for org-level properties
  - branch_protected instead of default_branch_protected
  - default_repo_permission instead of default_repository_permission
"""
import logging
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from database.models import Rule

log = logging.getLogger(__name__)

# ── Corrected Cypher queries keyed by rule ID ─────────────────────────────────
# Each query is rewritten to match our exact Neo4j node/relationship schema.

CORRECTED_QUERIES: dict[str, str] = {

    "CIS-GH-1.1.3": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE NOT repo.branch_protected
   OR coalesce(repo.required_approving_review_count, 0) < 2
RETURN repo.name AS repository,
       coalesce(repo.required_approving_review_count, 0) AS current_approvals,
       repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.1.4": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.branch_protected AND (repo.dismiss_stale_reviews = false OR repo.dismiss_stale_reviews IS NULL)
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.1.9": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.branch_protected AND (repo.require_status_checks = false OR repo.require_status_checks IS NULL)
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.1.12": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.branch_protected AND (repo.require_signed_commits = false OR repo.require_signed_commits IS NULL)
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.1.14": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.branch_protected AND (repo.enforce_admins = false OR repo.enforce_admins IS NULL)
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.1.16": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.branch_protected AND repo.allow_force_pushes = true
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.1.17": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.branch_protected AND repo.allow_deletions = true
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.1.20": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.branch_protected = false OR repo.branch_protected IS NULL
RETURN repo.name AS repository,
       repo.default_branch AS branch,
       repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.2.1": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.visibility = 'public'
  AND (repo.has_security_policy = false OR repo.has_security_policy IS NULL)
RETURN repo.name AS repository
""".strip(),

    "CIS-GH-1.2.7": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.last_pushed_days_ago IS NOT NULL
  AND repo.last_pushed_days_ago > 180
  AND (repo.archived = false OR repo.archived IS NULL)
RETURN repo.name AS repository,
       repo.last_pushed_days_ago AS days_inactive,
       repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.3.1": """
MATCH (u:User {platform: 'github'})-[:MEMBER_OF]->(org:Org {platform: 'github'})
WHERE u.last_activity_days_ago IS NOT NULL AND u.last_activity_days_ago > 90
RETURN u.username AS user,
       u.email AS email,
       u.last_activity_days_ago AS days_inactive,
       u.github_role AS role
""".strip(),

    "CIS-GH-1.3.3": """
MATCH (u:User {platform: 'github'})-[r:MEMBER_OF]->(org:Org {platform: 'github'})
WHERE r.role = 'admin'
WITH org, count(u) AS admin_count
WHERE admin_count < 2
RETURN org.name AS organization, admin_count
""".strip(),

    "CIS-GH-1.3.4": """
MATCH (u:User {platform: 'github'})-[:MEMBER_OF]->(org:Org {platform: 'github'})
WHERE u.two_factor = false OR u.two_factor IS NULL
RETURN u.username AS user,
       u.email AS email,
       u.github_role AS role
""".strip(),

    "CIS-GH-1.3.5": """
MATCH (org:Org {platform: 'github'})
WHERE org.two_factor_required = false OR org.two_factor_required IS NULL
RETURN org.name AS organization
""".strip(),

    "CIS-GH-1.3.7": """
MATCH (u:User)-[r:HAS_ROLE]->(repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE r.role = 'admin'
WITH repo, count(u) AS admin_count
WHERE admin_count < 2
RETURN repo.name AS repository, admin_count, repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.3.8": """
MATCH (org:Org {platform: 'github'})
WHERE org.default_repo_permission IN ['write', 'admin']
RETURN org.name AS organization,
       org.default_repo_permission AS default_permission
""".strip(),

    "CIS-GH-1.4.1": """
MATCH (org:Org {platform: 'github'})
WHERE org.oauth_app_restrictions_enabled = false OR org.oauth_app_restrictions_enabled IS NULL
RETURN org.name AS organization
""".strip(),

    "CIS-GH-1.4.3": """
MATCH (app:Application {platform: 'github'})-[r:CAN_ACCESS]->(org:Org)
WHERE size(r.scopes) > 5 OR 'admin:org' IN r.scopes
RETURN app.name AS application, r.scopes AS permissions, org.name AS organization
""".strip(),

    "CIS-GH-1.5.1": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.secret_scanning_enabled = false OR repo.secret_scanning_enabled IS NULL
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.5.4": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.code_scanning_enabled = false OR repo.code_scanning_enabled IS NULL
RETURN repo.name AS repository, repo.language AS language, repo.visibility AS visibility
""".strip(),

    "CIS-GH-1.5.5": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.dependabot_enabled = false OR repo.dependabot_enabled IS NULL
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CUSTOM-GH-001": """
MATCH (u:User {platform: 'github'})-[r:HAS_ROLE]->(repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE r.role = 'admin'
WITH u, count(repo) AS admin_repo_count, collect(repo.name) AS repos
WHERE admin_repo_count >= 5
RETURN u.username AS user, u.email AS email, admin_repo_count, repos
""".strip(),

    "CUSTOM-GH-002": """
MATCH (u:User {platform: 'github', is_external: true})-[r:HAS_ROLE]->(repo:Resource {platform: 'github'})
WHERE r.role IN ['write', 'admin']
RETURN u.username AS external_user, u.email AS email, repo.name AS repository, r.role AS access_level
""".strip(),

    "CUSTOM-GH-003": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE repo.visibility = 'public'
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CUSTOM-GH-004": """
MATCH (repo:Resource {platform: 'github', resource_subtype: 'repository'})
WHERE (repo.has_codeowners = false OR repo.has_codeowners IS NULL)
  AND (repo.visibility = 'private' OR repo.is_fork = false)
RETURN repo.name AS repository, repo.visibility AS visibility
""".strip(),

    "CUSTOM-GH-005": """
MATCH (repo:Resource {platform: 'github'})-[:HAS_WEBHOOK]->(webhook:Webhook)
WHERE webhook.url STARTS WITH 'http://' OR NOT webhook.has_secret
RETURN repo.name AS repository, webhook.url AS webhook_url, webhook.has_secret AS has_secret
""".strip(),
}

# Which column in the RETURN clause identifies the affected resource (for dedup)
RESOURCE_ID_FIELDS: dict[str, str] = {
    "CIS-GH-1.3.1": "user",
    "CIS-GH-1.3.3": "organization",
    "CIS-GH-1.3.4": "user",
    "CIS-GH-1.3.5": "organization",
    "CIS-GH-1.3.8": "organization",
    "CIS-GH-1.4.1": "organization",
    "CIS-GH-1.4.3": "application",
    "CUSTOM-GH-001": "user",
    "CUSTOM-GH-002": "external_user",
    # Jira rules
    "JIRA-AUTH-001": "organization",
    "JIRA-AUTH-002": "user",
    "JIRA-AUTH-003": "organization",
    "JIRA-AUTH-004": "organization",
    "JIRA-AUTH-005": "organization",
    "JIRA-ACCESS-001": "admin_count",
    "JIRA-ACCESS-002": "user",
    "JIRA-ACCESS-003": "project",
    "JIRA-ACCESS-004": "organization",
    "JIRA-ACCESS-005": "external_user",
    "JIRA-ACCESS-006": "user_count",
    "JIRA-ACCESS-007": "user",
    "JIRA-PROJECT-001": "project",
    "JIRA-PROJECT-002": "project",
    "JIRA-PROJECT-003": "project",
    "JIRA-APP-001": "application",
    "JIRA-APP-002": "application",
    "JIRA-APP-003": "organization",
    "JIRA-API-001": "user",
    "JIRA-API-002": "token_name",
    "JIRA-API-003": "service_account",
    "JIRA-AUDIT-001": "organization",
    "JIRA-AUDIT-002": "organization",
    "JIRA-DATA-001": "organization",
    "JIRA-DATA-002": "issue_key",
    "JIRA-CONFIG-001": "username",
    "JIRA-CONFIG-002": "organization",
    "JIRA-CONFIG-003": "organization",
    "JIRA-WORKFLOW-001": "workflow",
    "JIRA-WORKFLOW-002": "workflow",
    "JIRA-MOBILE-001": "organization",
    # Salesforce rules
    "SF-AUTH-001": "organization",
    "SF-AUTH-002": "organization",
    "SF-AUTH-003": "organization",
    "SF-AUTH-004": "count",
    "SF-USER-001": "user",
    "SF-USER-002": "user",
    "SF-USER-003": "organization",
    "SF-AUTHZ-001": "admin_count",
    "SF-AUTHZ-002": "user",
    "SF-AUTHZ-003": "user",
    "SF-AUTHZ-004": "user",
    "SF-AUTHZ-005": "user",
    "SF-EMERG-001": "emergency_account",
    "SF-EMERG-002": "emergency_account",
    "SF-SESS-001": "organization",
    "SF-SESS-002": "admin_user",
    "SF-APP-001": "organization",
    "SF-APP-002": "update_name",
    "SF-APP-003": "class_name",
    "SF-APP-004": "package_name",
    "SF-DATA-001": "field",
    "SF-DATA-002": "field",
    "SF-DATA-003": "sandbox_name",
    "SF-DATA-004": "organization",
    "SF-NET-001": "domain",
    "SF-NET-002": "apex_class",
    "SF-INT-001": "connected_app",
    "SF-INT-002": "integration_user",
    "SF-INT-003": "connected_app",
    "SF-CHG-001": "component",
    "SF-CHG-002": "organization",
    "SF-MON-001": "organization",
    "SF-MON-002": "organization",
    "SF-MON-003": "organization",
    "SF-COMP-001": "total_unclassified_fields",
    "SF-COMP-002": "object",
    "SF-LAND-001": "organization",
    "SF-LAND-002": "source_sandbox",
    # Entra ID rules
    "EID-AUTH-001": "user",
    "EID-AUTH-002": "user",
    "EID-AUTH-003": "tenant",
    "EID-AUTH-004": "tenant",
    "EID-AUTH-005": "tenant",
    "EID-IAM-001":  "admin_count",
    "EID-IAM-002":  "tenant",
    "EID-IAM-003":  "user",
    "EID-IAM-004":  "tenant",
    "EID-IAM-005":  "guest_user",
    "EID-IAM-006":  "tenant",
    "EID-CA-001":   "tenant",
    "EID-CA-002":   "tenant",
    "EID-CA-003":   "tenant",
    "EID-CA-004":   "admin",
    "EID-USR-001":  "tenant",
    "EID-USR-002":  "user",
    "EID-USR-003":  "shared_mailbox",
    "EID-APP-001":  "tenant",
    "EID-APP-002":  "service_principal",
    "EID-APP-003":  "application",
    "EID-APP-004":  "app",
    "EID-MON-001":  "tenant",
    "EID-MON-002":  "tenant",
    "EID-MON-003":  "user",
    "EID-MON-004":  "tenant",
    "EID-GRP-001":  "tenant",
    "EID-GRP-002":  "group_name",
    "EID-DEV-001":  "device",
    "EID-DEV-002":  "tenant",
    "EID-IDP-001":  "tenant",
    "EID-IDP-002":  "user",
    "EID-IDP-003":  "tenant",
    "EID-GOV-001":  "tenant",
    "EID-GOV-002":  "unmanaged_guests",
    "EID-GOV-003":  "tenant",
    "EID-XPLAT-001": "entra_identity",
    "EID-XPLAT-002": "user",
}
# Default for all others: "repository"

# ── Jira corrected queries ────────────────────────────────────────────────────
#
# The YAML queries are preserved as documentation. These corrected versions:
#   1. Use resource_subtype instead of resource_type  (schema consistency)
#   2. Simplify Permission node references → property checks on Application
#   3. Return empty for rules that need data unavailable in the Jira REST API
#      (2FA, SSO, domain verification, password policy, audit logs, last login)
#      These rules are kept active so they appear in the rules list but produce
#      no findings automatically — they require manual review or the Atlassian
#      Admin API connector (planned Phase 3).
#
_UNAVAILABLE = "MATCH (n:_Unavailable {dummy: true}) RETURN n.dummy AS dummy"

JIRA_CORRECTED_QUERIES: dict[str, str] = {

    # ── Auth / Identity ───────────────────────────────────────────────────────
    # JIRA-AUTH-001: org-level 2FA not exposed in REST API → no findings
    "JIRA-AUTH-001": _UNAVAILABLE,

    # JIRA-AUTH-002: per-user 2FA not exposed in REST API → no findings
    "JIRA-AUTH-002": _UNAVAILABLE,

    # JIRA-AUTH-003: SSO config requires Atlassian Admin API → no findings
    "JIRA-AUTH-003": _UNAVAILABLE,

    # JIRA-AUTH-004: domain verification requires Atlassian Admin API → no findings
    "JIRA-AUTH-004": _UNAVAILABLE,

    # JIRA-AUTH-005: password policy requires Atlassian Admin API → no findings
    "JIRA-AUTH-005": _UNAVAILABLE,

    # ── Access Control ────────────────────────────────────────────────────────
    # JIRA-ACCESS-001: detect global admins via group membership
    "JIRA-ACCESS-001": """
MATCH (u:User {platform: 'jira'})-[:MEMBER_OF]->(g:Group {platform: 'jira'})
WHERE g.name IN ['jira-administrators', 'jira-system-administrators', 'site-admins']
WITH count(u) AS admin_count, collect(u.email) AS admins
WHERE admin_count > 5
RETURN admin_count, admins
""".strip(),

    # JIRA-ACCESS-002: fix resource_type → resource_subtype
    "JIRA-ACCESS-002": """
MATCH (u:User {platform: 'jira'})-[r:HAS_ROLE]->(project:Resource {platform: 'jira', resource_subtype: 'project'})
WHERE r.role IN ['Administrators', 'Project Admin']
WITH u, count(project) AS admin_project_count, collect(project.name) AS projects
WHERE admin_project_count >= 10
RETURN u.username AS user, u.email AS email, admin_project_count, projects
""".strip(),

    # JIRA-ACCESS-003: fix resource_type → resource_subtype
    "JIRA-ACCESS-003": """
MATCH (project:Resource {platform: 'jira', resource_subtype: 'project'})
WHERE project.default_permission_scheme = true
RETURN project.name AS project,
       project.key AS project_key,
       project.permission_scheme_name AS scheme
""".strip(),

    # JIRA-ACCESS-004: public signup not exposed in REST API → no findings
    "JIRA-ACCESS-004": _UNAVAILABLE,

    # JIRA-ACCESS-005: fix resource_type → resource_subtype
    "JIRA-ACCESS-005": """
MATCH (u:User {platform: 'jira', is_external: true})-[r:HAS_ROLE]->(project:Resource {platform: 'jira', resource_subtype: 'project'})
WHERE r.role IN ['Administrators', 'Project Admin', 'Manage sprints']
RETURN u.email AS external_user,
       u.email_domain AS domain,
       project.name AS project,
       r.role AS role
""".strip(),

    # JIRA-ACCESS-006: HAS_PERMISSION→Permission not in schema → no findings
    "JIRA-ACCESS-006": _UNAVAILABLE,

    # JIRA-ACCESS-007: last_login not exposed in REST API → no findings
    "JIRA-ACCESS-007": _UNAVAILABLE,

    # ── Project Configuration ─────────────────────────────────────────────────
    # JIRA-PROJECT-001: fix resource_type → resource_subtype, fix exists() → IS NULL
    "JIRA-PROJECT-001": """
MATCH (project:Resource {platform: 'jira', resource_subtype: 'project'})
WHERE project.uses_project_roles IS NULL OR project.uses_project_roles = false
RETURN project.name AS project, project.key AS project_key
""".strip(),

    # JIRA-PROJECT-002: fix resource_type → resource_subtype
    "JIRA-PROJECT-002": """
MATCH (u:User)-[r:HAS_ROLE]->(project:Resource {platform: 'jira', resource_subtype: 'project'})
WHERE r.role IN ['Administrators', 'Project Admin']
WITH project, count(u) AS admin_count
WHERE admin_count = 1
RETURN project.name AS project, project.key AS project_key, admin_count
""".strip(),

    # JIRA-PROJECT-003: fix resource_type → resource_subtype, remove is_sensitive
    # (detects ALL projects without issue security scheme, not only 'sensitive' ones)
    "JIRA-PROJECT-003": """
MATCH (project:Resource {platform: 'jira', resource_subtype: 'project'})
WHERE project.has_security_scheme = false OR project.has_security_scheme IS NULL
RETURN project.name AS project, project.key AS project_key
""".strip(),

    # ── Third-party Apps ──────────────────────────────────────────────────────
    # JIRA-APP-001: simplify — store scopes on app node, no separate Permission nodes
    "JIRA-APP-001": """
MATCH (app:Application {platform: 'jira'})
WHERE any(scope IN app.scopes WHERE scope IN ['ADMIN', 'WRITE', 'ACT_AS_USER'])
RETURN app.name AS application, app.vendor AS vendor, app.scopes AS permissions
""".strip(),

    # JIRA-APP-002: unchanged (app.last_used_days_ago = null → no findings until API adds it)
    "JIRA-APP-002": """
MATCH (app:Application {platform: 'jira'})
WHERE app.last_used_days_ago > 90
RETURN app.name AS application,
       app.last_used_days_ago AS days_unused,
       app.installed_date AS installed
""".strip(),

    # JIRA-APP-003: check org group property
    "JIRA-APP-003": """
MATCH (org:Group {platform: 'jira', is_organization: true})
WHERE org.oauth_approval_required = false OR org.oauth_approval_required IS NULL
RETURN org.name AS organization
""".strip(),

    # ── API & Automation ──────────────────────────────────────────────────────
    # JIRA-API-001: uses_password_for_api not exposed in REST API → no findings
    "JIRA-API-001": _UNAVAILABLE,

    # JIRA-API-002: APIToken nodes not in schema → no findings
    "JIRA-API-002": _UNAVAILABLE,

    # JIRA-API-003: detect service/bot accounts without documented owner
    "JIRA-API-003": """
MATCH (u:User {platform: 'jira'})
WHERE u.account_type IN ['service', 'app']
  AND (u.email IS NULL OR u.email = '')
RETURN u.username AS service_account, u.account_type AS account_type
""".strip(),

    # ── Audit & Monitoring ────────────────────────────────────────────────────
    # JIRA-AUDIT-001/002: audit log settings not exposed in REST API → no findings
    "JIRA-AUDIT-001": _UNAVAILABLE,
    "JIRA-AUDIT-002": _UNAVAILABLE,

    # ── Data Protection ───────────────────────────────────────────────────────
    # JIRA-DATA-001: encryption settings not exposed in REST API → no findings
    "JIRA-DATA-001": _UNAVAILABLE,

    # JIRA-DATA-002: would require scanning issue content → out of scope for MVP
    "JIRA-DATA-002": _UNAVAILABLE,

    # ── Configuration ─────────────────────────────────────────────────────────
    # JIRA-CONFIG-001: detect default admin accounts still active
    "JIRA-CONFIG-001": """
MATCH (u:User {platform: 'jira'})
WHERE u.username IN ['admin', 'administrator', 'jira-admin', 'jira-administrator']
  AND u.is_active = true
RETURN u.username AS username, u.email AS email
""".strip(),

    # JIRA-CONFIG-002: CAPTCHA not exposed in REST API → no findings
    "JIRA-CONFIG-002": _UNAVAILABLE,

    # JIRA-CONFIG-003: SMTP settings not exposed in REST API → no findings
    "JIRA-CONFIG-003": _UNAVAILABLE,

    # ── Workflow ──────────────────────────────────────────────────────────────
    # JIRA-WORKFLOW-001: basic workflow check (transition restrictions not in REST API)
    "JIRA-WORKFLOW-001": """
MATCH (workflow:Workflow {platform: 'jira'})
WHERE workflow.has_transition_restrictions = false OR workflow.has_transition_restrictions IS NULL
RETURN workflow.name AS workflow
""".strip(),

    # JIRA-WORKFLOW-002: PostFunction nodes not in schema → no findings
    "JIRA-WORKFLOW-002": _UNAVAILABLE,

    # ── Mobile ────────────────────────────────────────────────────────────────
    # JIRA-MOBILE-001: mobile policy requires Atlassian Guard API → no findings
    "JIRA-MOBILE-001": _UNAVAILABLE,
}

# ── Salesforce corrected queries ──────────────────────────────────────────────
#
# YAML queries are preserved as documentation. These corrected versions:
#   1. Use Group {is_organization:true} instead of Organization label
#   2. Use User properties instead of Profile/Permission nodes
#   3. Use Application nodes instead of ConnectedApp label
#   4. Return empty for rules requiring Metadata/Tooling API / Shield / Event Monitoring
#      (those rules appear in the list but produce no findings automatically)
#
SALESFORCE_CORRECTED_QUERIES: dict[str, str] = {

    # ── Authentication ────────────────────────────────────────────────────────
    # SF-AUTH-001: MFA enforcement — requires Salesforce Identity API → no findings
    "SF-AUTH-001": _UNAVAILABLE,

    # SF-AUTH-002: password policy — requires Metadata API SecuritySettings → no findings
    "SF-AUTH-002": _UNAVAILABLE,

    # SF-AUTH-003: SSO config — requires Metadata API → no findings
    "SF-AUTH-003": _UNAVAILABLE,

    # SF-AUTH-004: profiles without login IP ranges — check profile group property
    "SF-AUTH-004": """
MATCH (g:Group {platform: 'salesforce', entity_subtype: 'profile'})
WHERE g.has_login_ip_ranges = false OR g.has_login_ip_ranges IS NULL
RETURN g.name AS profile, count(g) AS count
""".strip(),

    # ── User Management ───────────────────────────────────────────────────────
    # SF-USER-001: inactive users — last_login_days_ago stored on User node
    "SF-USER-001": """
MATCH (u:User {platform: 'salesforce'})
WHERE u.is_active = true
  AND u.last_login_days_ago > 90
RETURN u.username AS user,
       u.email AS email,
       u.last_login_days_ago AS days_inactive,
       u.profile AS profile
""".strip(),

    # SF-USER-002: sandbox users not sanitized — requires Sandbox API → no findings
    "SF-USER-002": _UNAVAILABLE,

    # SF-USER-003: centralized identity — org-level setting → no findings (always null)
    "SF-USER-003": _UNAVAILABLE,

    # ── Authorization ─────────────────────────────────────────────────────────
    # SF-AUTHZ-001: excessive sysadmins — profile stored on User node
    "SF-AUTHZ-001": """
MATCH (u:User {platform: 'salesforce'})
WHERE u.profile = 'System Administrator'
  AND u.is_active = true
WITH count(u) AS admin_count
WHERE admin_count > 5
RETURN admin_count, 'Exceeds recommended threshold of 5' AS finding
""".strip(),

    # SF-AUTHZ-002: ViewAllData — stored as property on User node
    "SF-AUTHZ-002": """
MATCH (u:User {platform: 'salesforce'})
WHERE u.has_view_all_data = true
  AND u.is_active = true
  AND u.profile <> 'System Administrator'
RETURN u.username AS user, u.profile AS profile, u.email AS email
""".strip(),

    # SF-AUTHZ-003: ModifyAllData — stored as property on User node
    "SF-AUTHZ-003": """
MATCH (u:User {platform: 'salesforce'})
WHERE u.has_modify_all_data = true
  AND u.is_active = true
  AND u.profile <> 'System Administrator'
RETURN u.username AS user, u.profile AS profile, u.email AS email
""".strip(),

    # SF-AUTHZ-004: AuthorApex — stored as property on User node
    "SF-AUTHZ-004": """
MATCH (u:User {platform: 'salesforce'})
WHERE u.has_author_apex = true
  AND u.is_active = true
RETURN u.username AS user, u.profile AS profile, u.role AS role
""".strip(),

    # SF-AUTHZ-005: SOD conflicts — requires full permission matrix → no findings
    "SF-AUTHZ-005": _UNAVAILABLE,

    # ── Emergency Access ──────────────────────────────────────────────────────
    # SF-EMERG-001: emergency accounts by username pattern
    "SF-EMERG-001": """
MATCH (u:User {platform: 'salesforce'})
WHERE (toLower(u.username) CONTAINS 'emergency'
    OR toLower(u.username) CONTAINS 'fireglass'
    OR toLower(u.username) CONTAINS 'breakglass')
  AND u.is_active = true
RETURN u.username AS emergency_account, u.email AS email
""".strip(),

    # SF-EMERG-002: emergency login monitoring — requires Event Monitoring → no findings
    "SF-EMERG-002": _UNAVAILABLE,

    # ── Session Security ──────────────────────────────────────────────────────
    # SF-SESS-001: session timeout — org property (null in REST API → no findings)
    "SF-SESS-001": """
MATCH (org:Group {platform: 'salesforce', is_organization: true})
WHERE org.session_timeout_minutes > 120
RETURN org.name AS organization,
       org.session_timeout_minutes AS current_timeout,
       'Should be <= 120 minutes' AS recommendation
""".strip(),

    # SF-SESS-002: login-as — requires Event Monitoring (AuditEvent) → no findings
    "SF-SESS-002": _UNAVAILABLE,

    # ── Application Security ──────────────────────────────────────────────────
    # SF-APP-001: Health Check score — org property (null in REST API → no findings)
    "SF-APP-001": """
MATCH (org:Group {platform: 'salesforce', is_organization: true})
WHERE org.health_check_score < 70
RETURN org.name AS organization,
       org.health_check_score AS current_score,
       'Below baseline standard' AS finding
""".strip(),

    # SF-APP-002: critical updates — requires Setup Metadata → no findings
    "SF-APP-002": _UNAVAILABLE,

    # SF-APP-003: insecure Apex code — requires static analysis → no findings
    "SF-APP-003": _UNAVAILABLE,

    # SF-APP-004: unreviewed AppExchange packages — requires Package2 API → no findings
    "SF-APP-004": _UNAVAILABLE,

    # ── Data Protection ───────────────────────────────────────────────────────
    # SF-DATA-001: Shield encryption — requires Salesforce Shield → no findings
    "SF-DATA-001": _UNAVAILABLE,

    # SF-DATA-002: field history — requires CustomField metadata → no findings
    "SF-DATA-002": _UNAVAILABLE,

    # SF-DATA-003: sandbox data masking — requires Sandbox API → no findings
    "SF-DATA-003": _UNAVAILABLE,

    # SF-DATA-004: event monitoring enabled — org property (null → no findings)
    "SF-DATA-004": """
MATCH (org:Group {platform: 'salesforce', is_organization: true})
WHERE org.event_monitoring_enabled = false
RETURN org.name AS organization,
       'Event Monitoring not licensed or enabled' AS finding
""".strip(),

    # ── Network Security ──────────────────────────────────────────────────────
    # SF-NET-001: HSTS — requires CustomDomain object (not queryable) → no findings
    "SF-NET-001": _UNAVAILABLE,

    # SF-NET-002: Apex HTTPS — requires code analysis → no findings
    "SF-NET-002": _UNAVAILABLE,

    # ── Integration Security ──────────────────────────────────────────────────
    # SF-INT-001: connected apps without IP restrictions
    "SF-INT-001": """
MATCH (app:Application {platform: 'salesforce'})
WHERE app.has_ip_restrictions = false OR app.has_ip_restrictions IS NULL
RETURN app.name AS connected_app,
       'No IP restrictions configured' AS finding
""".strip(),

    # SF-INT-002: integration user credential rotation — password age not in REST → no findings
    "SF-INT-002": _UNAVAILABLE,

    # SF-INT-003: overly permissive connected app scopes
    "SF-INT-003": """
MATCH (app:Application {platform: 'salesforce'})
WHERE 'full' IN app.oauth_scopes
   OR 'api' IN app.oauth_scopes
RETURN app.name AS connected_app,
       app.oauth_scopes AS granted_scopes,
       'Overly broad access' AS finding
""".strip(),

    # ── Change Management ─────────────────────────────────────────────────────
    # SF-CHG-001: prod changes without sandbox — requires MetadataChange tracking → no findings
    "SF-CHG-001": _UNAVAILABLE,

    # SF-CHG-002: version control — org property (null → no findings)
    "SF-CHG-002": """
MATCH (org:Group {platform: 'salesforce', is_organization: true})
WHERE org.version_control_enabled = false
RETURN org.name AS organization,
       'No version control detected' AS finding
""".strip(),

    # ── Monitoring ────────────────────────────────────────────────────────────
    # SF-MON-001: audit trail SIEM — org property (null → no findings)
    "SF-MON-001": """
MATCH (org:Group {platform: 'salesforce', is_organization: true})
WHERE org.audit_trail_siem_integration = false
RETURN org.name AS organization,
       'Setup Audit Trail not integrated with SIEM' AS finding
""".strip(),

    # SF-MON-002: login forensics — org property (null → no findings)
    "SF-MON-002": """
MATCH (org:Group {platform: 'salesforce', is_organization: true})
WHERE org.login_forensics_enabled = false
RETURN org.name AS organization
""".strip(),

    # SF-MON-003: transaction security — requires Metadata API → no findings
    "SF-MON-003": _UNAVAILABLE,

    # ── Compliance ────────────────────────────────────────────────────────────
    # SF-COMP-001: data classification — requires CustomField metadata → no findings
    "SF-COMP-001": _UNAVAILABLE,

    # SF-COMP-002: OWD sharing model — requires CustomObject metadata → no findings
    "SF-COMP-002": _UNAVAILABLE,

    # ── Landscape ─────────────────────────────────────────────────────────────
    # SF-LAND-001: My Domain deployed — org property (null → no findings)
    "SF-LAND-001": """
MATCH (org:Group {platform: 'salesforce', is_organization: true})
WHERE org.my_domain_deployed = false
RETURN org.name AS organization
""".strip(),

    # SF-LAND-002: cross-env interfaces — requires Sandbox/Environment API → no findings
    "SF-LAND-002": _UNAVAILABLE,
}

# ── Entra ID corrected queries ────────────────────────────────────────────────
#
# YAML queries reference Organization/DirectoryRole/ConditionalAccessPolicy labels.
# Our schema stores these as:
#   Organization         → Group {platform:'entraid', is_organization:true} with EntraOrg label
#   DirectoryRole        → Group {platform:'entraid', entity_subtype:'role'} with EntraRole label
#   ConditionalAccessPolicy → Application {platform:'entraid', entity_subtype:'ca_policy'}
#   ServicePrincipal     → Application {platform:'entraid', entity_subtype:'service_principal'}
#   Device               → Resource {platform:'entraid', resource_subtype:'device'}
#   HAS_ROLE (User→Role) → MEMBER_OF (User→Group)
#
ENTRAID_CORRECTED_QUERIES: dict[str, str] = {

    # ── Authentication ─────────────────────────────────────────────────────────
    # EID-AUTH-001: MFA for all users — mfa_registered property from userRegistrationDetails
    "EID-AUTH-001": """
MATCH (u:User {platform: 'entraid'})
WHERE u.mfa_registered = false
  AND u.is_active = true
  AND u.account_type <> 'ServiceAccount'
RETURN u.display_name AS user,
       u.user_principal_name AS upn,
       u.department AS department,
       u.created_date AS created
""".strip(),

    # EID-AUTH-002: MFA for privileged roles
    "EID-AUTH-002": """
MATCH (u:User {platform: 'entraid'})-[:HAS_ROLE]->(r:Group {platform: 'entraid', entity_subtype: 'role'})
WHERE r.is_privileged = true
  AND u.mfa_registered = false
  AND u.is_active = true
RETURN u.display_name AS user,
       u.user_principal_name AS upn,
       collect(r.name) AS privileged_roles
""".strip(),

    # EID-AUTH-003: Legacy auth blocked — computed from CA policies
    "EID-AUTH-003": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE org.legacy_auth_blocked = false
   OR org.legacy_auth_blocked IS NULL
RETURN org.name AS tenant,
       org.legacy_auth_blocked AS status,
       'Legacy authentication not blocked by Conditional Access' AS risk
""".strip(),

    # EID-AUTH-004: Password Hash Sync (hybrid only)
    "EID-AUTH-004": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE org.on_premises_sync_enabled = true
  AND (org.password_hash_sync_enabled = false OR org.password_hash_sync_enabled IS NULL)
RETURN org.name AS tenant,
       'Password Hash Sync disabled for hybrid environment' AS finding
""".strip(),

    # EID-AUTH-005: SSPR — not exposed via Graph API
    "EID-AUTH-005": _UNAVAILABLE,

    # ── Identity & Access Management ──────────────────────────────────────────
    # EID-IAM-001: Global Admin count
    "EID-IAM-001": """
MATCH (u:User {platform: 'entraid'})-[:HAS_ROLE]->(r:Group {platform: 'entraid', entity_subtype: 'role'})
WHERE r.name = 'Global Administrator'
  AND u.is_active = true
WITH count(u) AS admin_count
WHERE admin_count < 2 OR admin_count > 4
RETURN admin_count,
       CASE WHEN admin_count < 2
            THEN 'Too few Global Admins - single point of failure'
            ELSE 'Too many Global Admins - excess attack surface'
       END AS finding
""".strip(),

    # EID-IAM-002: PIM enabled
    "EID-IAM-002": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE org.pim_enabled = false OR org.pim_enabled IS NULL
RETURN org.name AS tenant,
       'PIM not licensed or enabled' AS finding
""".strip(),

    # EID-IAM-003: Permanent privileged role assignments
    "EID-IAM-003": """
MATCH (u:User {platform: 'entraid'})-[rel:HAS_ROLE]->(r:Group {platform: 'entraid', entity_subtype: 'role'})
WHERE r.is_privileged = true
  AND rel.assignment_type = 'active'
  AND u.is_active = true
  AND u.account_type <> 'ServiceAccount'
RETURN u.display_name AS user,
       u.user_principal_name AS upn,
       r.name AS permanent_role,
       rel.assigned_date AS assigned_since
""".strip(),

    # EID-IAM-004: Break-glass accounts — complex detection, not reliable
    "EID-IAM-004": _UNAVAILABLE,

    # EID-IAM-005: Inactive guest accounts
    "EID-IAM-005": """
MATCH (u:User {platform: 'entraid'})
WHERE u.user_type = 'Guest'
  AND u.is_active = true
  AND (u.last_sign_in_days_ago > 90 OR u.last_sign_in_days_ago IS NULL)
RETURN u.display_name AS guest_user,
       u.user_principal_name AS upn,
       u.last_sign_in_days_ago AS days_inactive,
       u.created_date AS created
""".strip(),

    # EID-IAM-006: Guest permissions too permissive
    "EID-IAM-006": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE org.guest_user_role_id = 'a0b1b346-4d3e-4e8b-98f8-753987be4970'
   OR org.guests_can_invite_others = true
   OR org.guest_access_restrictions = 'sameAsMembers'
RETURN org.name AS tenant,
       org.guest_access_restrictions AS current_restrictions,
       org.guests_can_invite_others AS can_invite
""".strip(),

    # ── Conditional Access ────────────────────────────────────────────────────
    # EID-CA-001: No CA policy for risky sign-ins
    "EID-CA-001": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE NOT EXISTS {
  MATCH (policy:Application {platform: 'entraid', entity_subtype: 'ca_policy'})
  WHERE policy.is_enabled = true
    AND 'signInRiskLevels' IN policy.conditions
}
RETURN org.name AS tenant,
       'No risky sign-in Conditional Access policy found' AS finding
""".strip(),

    # EID-CA-002: No CA policy for risky users
    "EID-CA-002": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE NOT EXISTS {
  MATCH (policy:Application {platform: 'entraid', entity_subtype: 'ca_policy'})
  WHERE policy.is_enabled = true
    AND 'userRiskLevels' IN policy.conditions
}
RETURN org.name AS tenant,
       'No user risk Conditional Access policy configured' AS finding
""".strip(),

    # EID-CA-003: No compliant-device CA policy
    "EID-CA-003": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE NOT EXISTS {
  MATCH (policy:Application {platform: 'entraid', entity_subtype: 'ca_policy'})
  WHERE policy.is_enabled = true
    AND 'compliantDevice' IN policy.grant_controls
}
RETURN org.name AS tenant,
       'No device compliance Conditional Access policy found' AS finding
""".strip(),

    # EID-CA-004: PAW enforcement — complex, requires Named Location inspection
    "EID-CA-004": _UNAVAILABLE,

    # ── User Security ─────────────────────────────────────────────────────────
    # EID-USR-001: Password expiry — not available via Graph API
    "EID-USR-001": _UNAVAILABLE,

    # EID-USR-002: Privileged accounts with on-prem sync
    "EID-USR-002": """
MATCH (u:User {platform: 'entraid'})-[:HAS_ROLE]->(r:Group {platform: 'entraid', entity_subtype: 'role'})
WHERE r.is_privileged = true
  AND u.on_premises_sync_enabled = true
  AND u.is_active = true
RETURN u.display_name AS user,
       u.user_principal_name AS upn,
       collect(r.name) AS privileged_roles,
       'Synced from on-premises - high risk' AS finding
""".strip(),

    # EID-USR-003: Shared mailbox — requires Exchange perms, not in Graph API
    "EID-USR-003": _UNAVAILABLE,

    # ── Application Security ──────────────────────────────────────────────────
    # EID-APP-001: User consent policy
    "EID-APP-001": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE org.user_consent_policy = 'allow_all'
   OR org.user_consent_policy IS NULL
RETURN org.name AS tenant,
       org.user_consent_policy AS current_policy,
       'Users can consent to third-party apps without admin approval' AS risk
""".strip(),

    # EID-APP-002: Service principals with privileged roles
    "EID-APP-002": """
MATCH (sp:Application {platform: 'entraid', entity_subtype: 'service_principal'})-[:HAS_ROLE]->(r:Group {platform: 'entraid', entity_subtype: 'role'})
WHERE r.is_privileged = true
RETURN sp.name AS service_principal,
       sp.app_id AS app_id,
       collect(r.name) AS dangerous_roles,
       sp.created_date AS created
""".strip(),

    # EID-APP-003: Client secrets — ClientSecret nodes not in schema
    "EID-APP-003": _UNAVAILABLE,

    # EID-APP-004: Unverified publisher perms — AppPermission nodes not in schema
    "EID-APP-004": _UNAVAILABLE,

    # ── Monitoring ────────────────────────────────────────────────────────────
    # EID-MON-001/002/003/004: require Azure Monitor / PIM alerts / RiskEvent / log settings
    "EID-MON-001": _UNAVAILABLE,
    "EID-MON-002": _UNAVAILABLE,
    "EID-MON-003": _UNAVAILABLE,
    "EID-MON-004": _UNAVAILABLE,

    # ── Group Management ──────────────────────────────────────────────────────
    # EID-GRP-001: Group creation restrictions
    "EID-GRP-001": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE org.users_can_create_security_groups = true
   OR org.users_can_create_m365_groups = true
RETURN org.name AS tenant,
       org.users_can_create_security_groups AS can_create_security,
       org.users_can_create_m365_groups AS can_create_m365
""".strip(),

    # EID-GRP-002: Dynamic group rules (flag all for manual review)
    "EID-GRP-002": """
MATCH (g:Group {platform: 'entraid', group_type: 'Dynamic'})
WHERE g.membership_rule IS NOT NULL
RETURN g.name AS group_name,
       g.membership_rule AS dynamic_rule,
       'Dynamic group requires periodic rule review' AS finding
""".strip(),

    # ── Device Management ─────────────────────────────────────────────────────
    # EID-DEV-001: Stale devices
    "EID-DEV-001": """
MATCH (d:Resource {platform: 'entraid', resource_subtype: 'device'})
WHERE d.is_enabled = true
  AND d.last_sign_in_days_ago > 90
RETURN d.name AS device,
       d.device_id AS device_id,
       d.operating_system AS os,
       d.last_sign_in_days_ago AS days_inactive
""".strip(),

    # EID-DEV-002: Device registration not restricted
    "EID-DEV-002": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE org.users_may_register_devices = 'All'
   OR (org.maximum_devices_per_user IS NOT NULL AND org.maximum_devices_per_user > 10)
   OR org.maximum_devices_per_user IS NULL
RETURN org.name AS tenant,
       org.users_may_register_devices AS registration_policy,
       org.maximum_devices_per_user AS max_devices
""".strip(),

    # ── Identity Protection ───────────────────────────────────────────────────
    # EID-IDP-001: Identity Protection not enabled (P2)
    "EID-IDP-001": """
MATCH (org:Group {platform: 'entraid', is_organization: true})
WHERE org.identity_protection_enabled = false
   OR org.identity_protection_enabled IS NULL
RETURN org.name AS tenant,
       org.p2_license_count AS p2_licenses,
       'Identity Protection not enabled' AS finding
""".strip(),

    # EID-IDP-002: Leaked credentials — Identity Protection P2 API
    "EID-IDP-002": _UNAVAILABLE,

    # EID-IDP-003: Password protection — not in Graph API
    "EID-IDP-003": _UNAVAILABLE,

    # ── Governance ────────────────────────────────────────────────────────────
    # EID-GOV-001/002/003: AccessReview / AccessPackage / TermsOfUse not in schema
    "EID-GOV-001": _UNAVAILABLE,
    "EID-GOV-002": _UNAVAILABLE,
    "EID-GOV-003": _UNAVAILABLE,

    # ── Cross-Platform ────────────────────────────────────────────────────────
    # EID-XPLAT-001: Highly privileged across multiple platforms
    "EID-XPLAT-001": """
MATCH (u1:User {platform: 'entraid'})-[:FEDERATED_IDENTITY]-(u2:User)
MATCH (u1)-[:HAS_ROLE]->(r1:Group {platform: 'entraid', entity_subtype: 'role'})
WHERE r1.is_privileged = true
MATCH (u2)-[r2:HAS_ROLE]->(res)
WHERE r2.role IN ['admin', 'owner', 'Owner', 'Admin', 'Administrator']
RETURN u1.user_principal_name AS entra_identity,
       u2.platform AS other_platform,
       u2.username AS platform_username,
       r1.name AS entra_role,
       r2.role AS platform_role,
       'Highly privileged across multiple platforms' AS alert
""".strip(),

    # EID-XPLAT-002: HR system cross-reference — hr_system_synced not available
    "EID-XPLAT-002": _UNAVAILABLE,
}

# Merge into unified lookup used by load_from_yaml
CORRECTED_QUERIES.update(JIRA_CORRECTED_QUERIES)
CORRECTED_QUERIES.update(SALESFORCE_CORRECTED_QUERIES)
CORRECTED_QUERIES.update(ENTRAID_CORRECTED_QUERIES)


def _infer_referential(platform: str) -> list[str]:
    """Map a platform tag to its default compliance standard(s)."""
    return ["CIS"]  # All Cypher-based rules are CIS-benchmarked


class RulesLoader:
    """Load rules from a YAML file into the rules table."""

    def __init__(self, db: Session):
        self._db = db

    def load_from_yaml(self, yaml_path: str) -> dict[str, Any]:
        """
        Parse YAML and upsert rules into the DB.

        Returns ``{"inserted": int, "updated": int, "errors": int, "error_details": list}``.
        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Rules file not found: {yaml_path}")

        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)

        rules_data: list[dict[str, Any]] = doc.get("rules", [])
        # Platform precedence: doc-level "platform" > doc-level "category" >
        # first rule's "platform" field > fallback "github"
        platform: str = (
            doc.get("platform")
            or doc.get("category")
            or (rules_data[0].get("platform") if rules_data else None)
            or "github"
        )

        inserted = updated = errors = 0
        error_details: list[str] = []

        for raw in rules_data:
            try:
                rule_id = raw["id"]
                corrected_query = CORRECTED_QUERIES.get(rule_id, raw.get("detection_query", ""))
                resource_id_field = RESOURCE_ID_FIELDS.get(rule_id, "repository")

                existing = self._db.get(Rule, rule_id)
                if existing:
                    existing.name = raw["name"]
                    existing.platform = raw.get("platform", platform)
                    existing.cis_control = raw.get("cis_control")
                    existing.severity = raw["severity"]
                    existing.category = raw["category"]
                    existing.profile = raw.get("profile")
                    existing.description = raw.get("description", "")
                    existing.rationale = raw.get("rationale", "")
                    existing.detection_query = corrected_query
                    existing.resource_id_field = resource_id_field
                    existing.remediation = raw.get("remediation", "")
                    existing.compliance_mapping = raw.get("compliance_mapping", [])
                    existing.referentials = raw.get("referentials", _infer_referential(raw.get("platform", platform)))
                    updated += 1
                else:
                    rule = Rule(
                        id=rule_id,
                        name=raw["name"],
                        platform=raw.get("platform", platform),
                        cis_control=raw.get("cis_control"),
                        severity=raw["severity"],
                        category=raw["category"],
                        profile=raw.get("profile"),
                        description=raw.get("description", ""),
                        rationale=raw.get("rationale", ""),
                        detection_query=corrected_query,
                        query_type="cypher",
                        resource_id_field=resource_id_field,
                        remediation=raw.get("remediation", ""),
                        compliance_mapping=raw.get("compliance_mapping", []),
                        referentials=raw.get("referentials", _infer_referential(raw.get("platform", platform))),
                        is_active=True,
                    )
                    self._db.add(rule)
                    inserted += 1
            except Exception as exc:
                errors += 1
                error_details.append(f"{raw.get('id', '?')}: {exc}")
                log.warning("rule_load_error", extra={"rule": raw.get("id"), "error": str(exc)})

        self._db.commit()
        result: dict[str, Any] = {
            "inserted": inserted,
            "updated": updated,
            "errors": errors,
            "error_details": error_details,
        }
        log.info("rules_loaded", extra={**result, "platform": platform, "file": yaml_path})
        return result

    def load_all_github_rules(self, base_dir: str = ".") -> dict[str, Any]:
        """Load github_cis_rules.yaml from base_dir."""
        yaml_path = str(Path(base_dir) / "github_cis_rules.yaml")
        return self.load_from_yaml(yaml_path)

    def load_all_jira_rules(self, base_dir: str = ".") -> dict[str, Any]:
        """Load jira_security_rules.yaml from base_dir."""
        yaml_path = str(Path(base_dir) / "jira_security_rules.yaml")
        return self.load_from_yaml(yaml_path)

    def load_all_salesforce_rules(self, base_dir: str = ".") -> dict[str, Any]:
        """Load salesforce_security_rules.yaml from base_dir."""
        yaml_path = str(Path(base_dir) / "salesforce_security_rules.yaml")
        return self.load_from_yaml(yaml_path)

    def load_all_entraid_rules(self, base_dir: str = ".") -> dict[str, Any]:
        """Load entraid_security_rules.yaml from base_dir."""
        yaml_path = str(Path(base_dir) / "entraid_security_rules.yaml")
        return self.load_from_yaml(yaml_path)

    def load_all_soc2_rules(self, base_dir: str = ".") -> dict[str, Any]:
        """Load soc2_security_rules.yaml from base_dir."""
        yaml_path = str(Path(base_dir) / "soc2_security_rules.yaml")
        return self.load_from_yaml(yaml_path)
