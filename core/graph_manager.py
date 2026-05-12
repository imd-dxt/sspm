"""
Neo4j graph manager.

Node labels:  User, Group, Resource, Org
Relationships: MEMBER_OF, HAS_ROLE, BELONGS_TO, PART_OF
"""
import logging
from contextlib import contextmanager
from typing import Any, Generator

from neo4j import GraphDatabase, Driver, Session

from config.settings import settings

log = logging.getLogger(__name__)


class GraphManager:
    """Manages Neo4j connectivity and bulk import operations."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self._driver: Driver = GraphDatabase.driver(
            uri or settings.neo4j_uri,
            auth=(user or settings.neo4j_user, password or settings.neo4j_password),
        )

    def close(self) -> None:
        self._driver.close()

    @contextmanager
    def _session(self) -> Generator[Session, None, None]:
        with self._driver.session() as session:
            yield session

    # ── Schema init ───────────────────────────────────────────────────────────

    def create_constraints(self) -> None:
        """
        Create index constraints on the uid property (platform:platform_id).
        Uses a single-property unique constraint — compatible with Neo4j Community.
        """
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (u:User)        REQUIRE u.uid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (g:Group)       REQUIRE g.uid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Resource)    REQUIRE r.uid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (o:Org)         REQUIRE o.uid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Application) REQUIRE a.uid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (w:Workflow)    REQUIRE w.uid IS UNIQUE",
        ]
        with self._session() as session:
            for stmt in constraints:
                try:
                    session.run(stmt)
                except Exception as exc:
                    log.warning("constraint_skipped", extra={"stmt": stmt[:60], "error": str(exc)})
        log.info("neo4j_constraints_done")

    # ── Node upserts ──────────────────────────────────────────────────────────

    def upsert_user(self, data: dict[str, Any]) -> None:
        meta = data.get("metadata", {})
        uid = f"{data['platform']}:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (u:User {uid: $uid})
                SET   u.platform     = $platform,
                      u.platform_id  = $platform_id,
                      u.username     = $username,
                      u.display_name = $display_name,
                      u.email        = $email,
                      u.is_active    = $is_active,
                      u.is_external  = $is_external,
                      u.two_factor   = $two_factor,
                      u.github_role  = $github_role,
                      u.updated_at   = timestamp()
                """,
                uid=uid,
                platform=data["platform"],
                platform_id=data["platform_id"],
                username=data.get("username"),
                display_name=data.get("display_name"),
                email=data.get("email"),
                is_active=data.get("is_active", True),
                is_external=data.get("is_external", False),
                two_factor=meta.get("two_factor_enabled"),
                github_role=meta.get("github_role"),
            )

    def upsert_group(self, data: dict[str, Any]) -> None:
        meta = data.get("metadata", {})
        uid = f"{data['platform']}:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (g:Group {uid: $uid})
                SET   g.platform    = $platform,
                      g.platform_id = $platform_id,
                      g.name        = $name,
                      g.description = $description,
                      g.slug        = $slug,
                      g.updated_at  = timestamp()
                """,
                uid=uid,
                platform=data["platform"],
                platform_id=data["platform_id"],
                name=data.get("name"),
                description=data.get("description"),
                slug=meta.get("slug"),
            )

    def upsert_resource(self, data: dict[str, Any]) -> None:
        meta = data.get("metadata", {})
        uid = f"{data['platform']}:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (r:Resource {uid: $uid})
                SET   r.platform                       = $platform,
                      r.platform_id                    = $platform_id,
                      r.name                           = $name,
                      r.resource_subtype               = $subtype,
                      r.is_public                      = $is_public,
                      r.visibility                     = $visibility,
                      r.default_branch                 = $default_branch,
                      r.archived                       = $archived,
                      r.is_fork                        = $is_fork,
                      r.language                       = $language,
                      r.last_pushed_days_ago           = $last_pushed_days_ago,
                      r.branch_protected               = $branch_protected,
                      r.allow_force_pushes             = $allow_force_pushes,
                      r.allow_deletions                = $allow_deletions,
                      r.enforce_admins                 = $enforce_admins,
                      r.required_pr_reviews            = $required_pr_reviews,
                      r.required_approving_review_count= $review_count,
                      r.dismiss_stale_reviews          = $dismiss_stale,
                      r.require_code_owner_reviews     = $codeowner_reviews,
                      r.require_status_checks          = $require_status_checks,
                      r.require_signed_commits         = $require_signed_commits,
                      r.secret_scanning_enabled        = $secret_scanning,
                      r.code_scanning_enabled          = $code_scanning,
                      r.dependabot_enabled             = $dependabot,
                      r.has_security_policy            = $has_security_policy,
                      r.has_codeowners                 = $has_codeowners,
                      r.resource_type                  = $subtype,
                      r.updated_at                     = timestamp()
                """,
                uid=uid,
                platform=data["platform"],
                platform_id=data["platform_id"],
                name=data.get("name"),
                subtype=data.get("resource_subtype"),
                is_public=data.get("is_public", False),
                visibility=meta.get("visibility"),
                default_branch=meta.get("default_branch"),
                archived=meta.get("archived", False),
                is_fork=meta.get("is_fork", False),
                language=meta.get("language"),
                last_pushed_days_ago=meta.get("last_pushed_days_ago"),
                branch_protected=meta.get("branch_protected", False),
                allow_force_pushes=meta.get("allow_force_pushes", True),
                allow_deletions=meta.get("allow_deletions", True),
                enforce_admins=meta.get("enforce_admins", False),
                required_pr_reviews=meta.get("required_pr_reviews", False),
                review_count=meta.get("required_approving_review_count", 0),
                dismiss_stale=meta.get("dismiss_stale_reviews", False),
                codeowner_reviews=meta.get("require_code_owner_reviews", False),
                require_status_checks=meta.get("require_status_checks", False),
                require_signed_commits=meta.get("require_signed_commits", False),
                secret_scanning=meta.get("secret_scanning_enabled", False),
                code_scanning=meta.get("code_scanning_enabled", False),
                dependabot=meta.get("dependabot_enabled", False),
                has_security_policy=meta.get("has_security_policy", False),
                has_codeowners=meta.get("has_codeowners", False),
            )

    def upsert_org(self, platform: str, org_id: str, name: str, **props: Any) -> None:
        uid = f"{platform}:{org_id}"
        with self._session() as session:
            session.run(
                """
                MERGE (o:Org {uid: $uid})
                SET   o.platform    = $platform,
                      o.platform_id = $platform_id,
                      o.name        = $name,
                      o.two_factor_required        = $two_factor_required,
                      o.default_repo_permission    = $default_repo_permission,
                      o.members_can_create_repos   = $members_can_create_repos,
                      o.updated_at  = timestamp()
                """,
                uid=uid,
                platform=platform,
                platform_id=org_id,
                name=name,
                two_factor_required=props.get("two_factor_required"),
                default_repo_permission=props.get("default_repo_permission"),
                members_can_create_repos=props.get("members_can_create_repos"),
            )

    def upsert_jira_org_group(self, data: dict[str, Any]) -> None:
        """
        Upsert the special Jira organization Group node.

        Stores org-level security settings as properties on a Group node with
        is_organization=true so YAML rules can query them via:
            MATCH (org:Group {platform: 'jira', is_organization: true})
        """
        meta = data.get("metadata", {})
        uid = "jira:org"
        with self._session() as session:
            session.run(
                """
                MERGE (g:Group {uid: $uid})
                SET   g:JiraGroup,
                      g.platform                   = 'jira',
                      g.platform_id                = 'org',
                      g.name                       = $name,
                      g.caption                    = $name,
                      g.is_organization            = true,
                      g.domain                     = $domain,
                      g.total_users                = $total_users,
                      g.permission_schemes_count   = $perm_scheme_count,
                      g.two_factor_required        = $two_factor_required,
                      g.sso_enabled                = $sso_enabled,
                      g.domain_verified            = $domain_verified,
                      g.public_signup_enabled      = $public_signup_enabled,
                      g.oauth_approval_required    = $oauth_approval_required,
                      g.audit_log_retention_days   = $audit_log_retention_days,
                      g.audit_log_forwarding_enabled = $audit_log_forwarding,
                      g.encryption_at_rest_enabled = $encryption_at_rest,
                      g.captcha_enabled            = $captcha_enabled,
                      g.smtp_tls_enabled           = $smtp_tls_enabled,
                      g.smtp_server                = $smtp_server,
                      g.mobile_policy_enabled      = $mobile_policy_enabled,
                      g.password_min_length        = $password_min_length,
                      g.password_complexity_required = $password_complexity,
                      g.updated_at                 = timestamp()
                """,
                uid=uid,
                name=data.get("name", "organization"),
                domain=meta.get("domain"),
                total_users=meta.get("total_users"),
                perm_scheme_count=meta.get("permission_schemes_count"),
                two_factor_required=meta.get("two_factor_required"),
                sso_enabled=meta.get("sso_enabled"),
                domain_verified=meta.get("domain_verified"),
                public_signup_enabled=meta.get("public_signup_enabled"),
                oauth_approval_required=meta.get("oauth_approval_required"),
                audit_log_retention_days=meta.get("audit_log_retention_days"),
                audit_log_forwarding=meta.get("audit_log_forwarding_enabled"),
                encryption_at_rest=meta.get("encryption_at_rest_enabled"),
                captcha_enabled=meta.get("captcha_enabled"),
                smtp_tls_enabled=meta.get("smtp_tls_enabled"),
                smtp_server=meta.get("smtp_server"),
                mobile_policy_enabled=meta.get("mobile_policy_enabled"),
                password_min_length=meta.get("password_min_length"),
                password_complexity=meta.get("password_complexity_required"),
            )

    def upsert_jira_project(self, data: dict[str, Any]) -> None:
        """Upsert a Jira project as a Resource node with project-specific properties."""
        meta = data.get("metadata", {})
        uid = f"jira:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (r:Resource {uid: $uid})
                SET   r:JiraProject,
                      r.platform                 = 'jira',
                      r.platform_id              = $platform_id,
                      r.name                     = $name,
                      r.resource_subtype         = 'project',
                      r.resource_type            = 'project',
                      r.key                      = $key,
                      r.project_type             = $project_type,
                      r.style                    = $style,
                      r.is_private               = $is_private,
                      r.is_public                = $is_public,
                      r.lead                     = $lead,
                      r.permission_scheme_id     = $perm_scheme_id,
                      r.permission_scheme_name   = $perm_scheme_name,
                      r.default_permission_scheme = $default_perm_scheme,
                      r.browse_permission        = $browse_permission,
                      r.security_scheme_id       = $security_scheme_id,
                      r.has_security_scheme      = $has_security_scheme,
                      r.uses_project_roles       = $uses_project_roles,
                      r.caption                  = $caption,
                      r.updated_at               = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                name=data.get("name", ""),
                key=meta.get("key"),
                project_type=meta.get("project_type"),
                style=meta.get("style"),
                is_private=meta.get("is_private", False),
                is_public=data.get("is_public", not meta.get("is_private", False)),
                lead=meta.get("lead"),
                perm_scheme_id=meta.get("permission_scheme_id"),
                perm_scheme_name=meta.get("permission_scheme_name"),
                default_perm_scheme=meta.get("default_permission_scheme", False),
                browse_permission=meta.get("browse_permission"),
                security_scheme_id=meta.get("security_scheme_id"),
                has_security_scheme=meta.get("has_security_scheme", False),
                uses_project_roles=meta.get("uses_project_roles", True),
                caption=f"{meta.get('key', '')} · {data.get('name', '')}".strip(" ·"),
            )

    def upsert_application(self, data: dict[str, Any]) -> None:
        """Upsert a third-party application node (Jira Marketplace app)."""
        meta = data.get("metadata", {})
        uid = f"jira:{data.get('platform_id', data.get('name', ''))}"
        with self._session() as session:
            session.run(
                """
                MERGE (a:Application {uid: $uid})
                SET   a.platform          = 'jira',
                      a.platform_id       = $platform_id,
                      a.name              = $name,
                      a.key               = $key,
                      a.vendor            = $vendor,
                      a.version           = $version,
                      a.scopes            = $scopes,
                      a.enabled           = $enabled,
                      a.installed_date    = $installed_date,
                      a.last_used_days_ago = $last_used_days_ago,
                      a.updated_at        = timestamp()
                """,
                uid=uid,
                platform_id=data.get("platform_id", ""),
                name=data.get("name", ""),
                key=meta.get("key"),
                vendor=meta.get("vendor"),
                version=meta.get("version"),
                scopes=meta.get("scopes", []),
                enabled=data.get("is_active", True),
                installed_date=meta.get("installed_date"),
                last_used_days_ago=meta.get("last_used_days_ago"),
            )

    def upsert_workflow(self, data: dict[str, Any]) -> None:
        """Upsert a Jira workflow node."""
        meta = data.get("metadata", {})
        uid = f"jira:workflow:{data.get('platform_id', data.get('name', ''))}"
        with self._session() as session:
            session.run(
                """
                MERGE (w:Workflow {uid: $uid})
                SET   w.platform                    = 'jira',
                      w.name                        = $name,
                      w.has_transition_restrictions  = $has_transition_restrictions,
                      w.projects                    = $projects,
                      w.updated_at                  = timestamp()
                """,
                uid=uid,
                name=data.get("name", ""),
                has_transition_restrictions=meta.get("has_transition_restrictions", False),
                projects=meta.get("projects", []),
            )

    # ── Salesforce node upserts ───────────────────────────────────────────────

    def upsert_salesforce_org_group(self, data: dict[str, Any]) -> None:
        """
        Upsert the Salesforce organization Group node.

        Most security settings (MFA, password policy, SSO, Health Check) are
        only accessible via Metadata/Tooling API and will be null here.
        Rules checking these will produce no findings until Phase 4 adds those APIs.
        """
        meta = data.get("metadata", {})
        uid  = "salesforce:org"
        with self._session() as session:
            session.run(
                """
                MERGE (g:Group {uid: $uid})
                SET   g:SalesforceOrg,
                      g.platform                     = 'salesforce',
                      g.platform_id                  = 'org',
                      g.name                         = $name,
                      g.caption                      = $name,
                      g.is_organization              = true,
                      g.org_id                       = $org_id,
                      g.instance_url                 = $instance_url,
                      g.org_type                     = $org_type,
                      g.is_sandbox                   = $is_sandbox,
                      g.total_users                  = $total_users,
                      g.mfa_required                 = $mfa_required,
                      g.password_min_length          = $password_min_length,
                      g.password_complexity          = $password_complexity,
                      g.password_history_restriction = $password_history,
                      g.password_max_age             = $password_max_age,
                      g.sso_enabled                  = $sso_enabled,
                      g.health_check_score           = $health_check_score,
                      g.session_timeout_minutes      = $session_timeout,
                      g.event_monitoring_enabled     = $event_monitoring,
                      g.my_domain_deployed           = $my_domain_deployed,
                      g.version_control_enabled      = $version_control,
                      g.audit_trail_siem_integration = $audit_trail_siem,
                      g.login_forensics_enabled      = $login_forensics,
                      g.scim_enabled                 = $scim_enabled,
                      g.updated_at                   = timestamp()
                """,
                uid=uid,
                name=data.get("name", "Salesforce Org"),
                org_id=meta.get("org_id"),
                instance_url=meta.get("instance_url"),
                org_type=meta.get("org_type"),
                is_sandbox=meta.get("is_sandbox", False),
                total_users=meta.get("total_users"),
                mfa_required=meta.get("mfa_required"),
                password_min_length=meta.get("password_min_length"),
                password_complexity=meta.get("password_complexity"),
                password_history=meta.get("password_history_restriction"),
                password_max_age=meta.get("password_max_age"),
                sso_enabled=meta.get("sso_enabled"),
                health_check_score=meta.get("health_check_score"),
                session_timeout=meta.get("session_timeout_minutes"),
                event_monitoring=meta.get("event_monitoring_enabled"),
                my_domain_deployed=meta.get("my_domain_deployed"),
                version_control=meta.get("version_control_enabled"),
                audit_trail_siem=meta.get("audit_trail_siem_integration"),
                login_forensics=meta.get("login_forensics_enabled"),
                scim_enabled=meta.get("scim_enabled"),
            )

    def upsert_salesforce_user(self, data: dict[str, Any]) -> None:
        """
        Upsert a Salesforce user with profile, role, last login, and
        dangerous permission flags.
        """
        meta = data.get("metadata", {})
        uid  = f"salesforce:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (u:User {uid: $uid})
                SET   u:SalesforceUser,
                      u.platform              = 'salesforce',
                      u.platform_id           = $platform_id,
                      u.username              = $username,
                      u.display_name          = $display_name,
                      u.email                 = $email,
                      u.is_active             = $is_active,
                      u.is_external           = $is_external,
                      u.profile               = $profile,
                      u.role                  = $role,
                      u.user_type             = $user_type,
                      u.last_login_days_ago   = $last_login_days_ago,
                      u.is_integration_user   = $is_integration_user,
                      u.has_view_all_data     = $has_view_all_data,
                      u.has_modify_all_data   = $has_modify_all_data,
                      u.has_author_apex       = $has_author_apex,
                      u.mfa_enabled           = $mfa_enabled,
                      u.has_login_ip_ranges   = $has_login_ip_ranges,
                      u.caption               = $caption,
                      u.updated_at            = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                username=data.get("username"),
                display_name=data.get("display_name"),
                email=data.get("email"),
                is_active=data.get("is_active", True),
                is_external=data.get("is_external", False),
                profile=meta.get("profile"),
                role=meta.get("role"),
                user_type=meta.get("user_type", "Standard"),
                last_login_days_ago=meta.get("last_login_days_ago"),
                is_integration_user=meta.get("is_integration_user", False),
                has_view_all_data=meta.get("has_view_all_data", False),
                has_modify_all_data=meta.get("has_modify_all_data", False),
                has_author_apex=meta.get("has_author_apex", False),
                mfa_enabled=meta.get("mfa_enabled"),
                has_login_ip_ranges=meta.get("has_login_ip_ranges"),
                caption=data.get("display_name") or data.get("username") or data.get("platform_id", ""),
            )

    def upsert_salesforce_profile_group(self, data: dict[str, Any]) -> None:
        """Upsert a Salesforce Profile as a Group node with SalesforceProfile label."""
        meta = data.get("metadata", {})
        uid  = f"salesforce:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (g:Group {uid: $uid})
                SET   g:SalesforceProfile,
                      g.platform             = 'salesforce',
                      g.platform_id          = $platform_id,
                      g.name                 = $name,
                      g.caption              = $name,
                      g.entity_subtype       = 'profile',
                      g.license              = $license,
                      g.has_login_ip_ranges  = $has_login_ip_ranges,
                      g.updated_at           = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                name=data.get("name", ""),
                license=meta.get("license"),
                has_login_ip_ranges=meta.get("has_login_ip_ranges", False),
            )

    def upsert_salesforce_app(self, data: dict[str, Any]) -> None:
        """Upsert a Salesforce Connected App as an Application node."""
        meta = data.get("metadata", {})
        uid  = f"salesforce:{data.get('platform_id', data.get('name', ''))}"
        with self._session() as session:
            session.run(
                """
                MERGE (a:Application {uid: $uid})
                SET   a:SalesforceApp,
                      a.platform             = 'salesforce',
                      a.platform_id          = $platform_id,
                      a.name                 = $name,
                      a.contact_email        = $contact_email,
                      a.admin_approved_only  = $admin_approved_only,
                      a.oauth_scopes         = $oauth_scopes,
                      a.has_ip_restrictions  = $has_ip_restrictions,
                      a.ip_ranges            = $ip_ranges,
                      a.enabled              = true,
                      a.updated_at           = timestamp()
                """,
                uid=uid,
                platform_id=data.get("platform_id", ""),
                name=data.get("name", ""),
                contact_email=meta.get("contact_email"),
                admin_approved_only=meta.get("admin_approved_only", False),
                oauth_scopes=meta.get("oauth_scopes", []),
                has_ip_restrictions=meta.get("has_ip_restrictions"),
                ip_ranges=meta.get("ip_ranges", []),
            )

    # ── (end Salesforce upserts) ──────────────────────────────────────────────

    # ── Entra ID node upserts ─────────────────────────────────────────────────

    def upsert_entraid_org(self, data: dict[str, Any]) -> None:
        """Upsert the Entra ID tenant organization Group node."""
        meta = data.get("metadata", {})
        uid  = "entraid:org"
        with self._session() as session:
            session.run(
                """
                MERGE (g:Group {uid: $uid})
                SET   g:EntraOrg,
                      g.platform                         = 'entraid',
                      g.platform_id                      = 'org',
                      g.name                             = $name,
                      g.caption                          = $name,
                      g.is_organization                  = true,
                      g.tenant_id                        = $tenant_id,
                      g.tenant_name                      = $tenant_name,
                      g.on_premises_sync_enabled         = $on_prem_sync,
                      g.security_defaults_enabled        = $sec_defaults,
                      g.legacy_auth_blocked              = $legacy_auth_blocked,
                      g.guest_user_role_id               = $guest_user_role_id,
                      g.guests_can_invite_others         = $guests_can_invite,
                      g.guest_access_restrictions        = $guest_access,
                      g.user_consent_policy              = $user_consent_policy,
                      g.users_can_create_security_groups = $can_create_sg,
                      g.users_can_create_m365_groups     = $can_create_m365,
                      g.pim_enabled                      = $pim_enabled,
                      g.identity_protection_enabled      = $idp_enabled,
                      g.p2_license_count                 = $p2_licenses,
                      g.users_may_register_devices       = $may_register_devices,
                      g.maximum_devices_per_user         = $max_devices,
                      g.password_hash_sync_enabled       = $phs_enabled,
                      g.sspr_enabled                     = $sspr_enabled,
                      g.sspr_auth_methods_required       = $sspr_methods,
                      g.diagnostic_logs_enabled          = $diag_logs,
                      g.audit_log_retention_days         = $audit_retention,
                      g.mfa_required                     = $mfa_required,
                      g.updated_at                       = timestamp()
                """,
                uid=uid,
                name=data.get("name", "Entra ID Tenant"),
                tenant_id=meta.get("tenant_id"),
                tenant_name=meta.get("tenant_name"),
                on_prem_sync=meta.get("on_premises_sync_enabled", False),
                sec_defaults=meta.get("security_defaults_enabled"),
                legacy_auth_blocked=meta.get("legacy_auth_blocked"),
                guest_user_role_id=meta.get("guest_user_role_id"),
                guests_can_invite=meta.get("guests_can_invite_others"),
                guest_access=meta.get("guest_access_restrictions"),
                user_consent_policy=meta.get("user_consent_policy"),
                can_create_sg=meta.get("users_can_create_security_groups"),
                can_create_m365=meta.get("users_can_create_m365_groups"),
                pim_enabled=meta.get("pim_enabled"),
                idp_enabled=meta.get("identity_protection_enabled"),
                p2_licenses=meta.get("p2_license_count"),
                may_register_devices=meta.get("users_may_register_devices"),
                max_devices=meta.get("maximum_devices_per_user"),
                phs_enabled=meta.get("password_hash_sync_enabled"),
                sspr_enabled=meta.get("sspr_enabled"),
                sspr_methods=meta.get("sspr_auth_methods_required"),
                diag_logs=meta.get("diagnostic_logs_enabled"),
                audit_retention=meta.get("audit_log_retention_days"),
                mfa_required=meta.get("mfa_required"),
            )

    def upsert_entraid_user(self, data: dict[str, Any]) -> None:
        """Upsert an Entra ID user node."""
        meta = data.get("metadata", {})
        uid  = f"entraid:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (u:User {uid: $uid})
                SET   u:EntraUser,
                      u.platform                  = 'entraid',
                      u.platform_id               = $platform_id,
                      u.username                  = $username,
                      u.display_name              = $display_name,
                      u.email                     = $email,
                      u.is_active                 = $is_active,
                      u.is_external               = $is_external,
                      u.user_principal_name       = $upn,
                      u.user_type                 = $user_type,
                      u.account_type              = $account_type,
                      u.job_title                 = $job_title,
                      u.department                = $department,
                      u.on_premises_sync_enabled  = $on_prem_sync,
                      u.created_date              = $created_date,
                      u.last_sign_in_days_ago     = $last_sign_in_days,
                      u.mfa_registered            = $mfa_registered,
                      u.mfa_enabled               = $mfa_registered,
                      u.mfa_capable               = $mfa_capable,
                      u.risk_state                = $risk_state,
                      u.risk_level                = $risk_level,
                      u.risk_remediated           = $risk_remediated,
                      u.is_break_glass            = $is_break_glass,
                      u.sign_in_blocked           = $sign_in_blocked,
                      u.account_enabled           = $account_enabled,
                      u.caption                   = $caption,
                      u.updated_at                = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                username=data.get("username"),
                display_name=data.get("display_name"),
                email=data.get("email"),
                is_active=data.get("is_active", True),
                is_external=data.get("is_external", False),
                upn=data.get("username"),
                user_type=meta.get("user_type", "Member"),
                account_type=meta.get("account_type", "UserAccount"),
                job_title=meta.get("job_title"),
                department=meta.get("department"),
                on_prem_sync=meta.get("on_premises_sync_enabled", False),
                created_date=meta.get("created_date"),
                last_sign_in_days=meta.get("last_sign_in_days_ago"),
                mfa_registered=meta.get("mfa_registered"),
                mfa_capable=meta.get("mfa_capable"),
                risk_state=meta.get("risk_state"),
                risk_level=meta.get("risk_level"),
                risk_remediated=meta.get("risk_remediated"),
                is_break_glass=meta.get("is_break_glass", False),
                sign_in_blocked=meta.get("sign_in_blocked", False),
                account_enabled=meta.get("account_enabled", True),
                caption=data.get("display_name") or data.get("username") or data.get("platform_id", ""),
            )

    def upsert_entraid_role(self, data: dict[str, Any]) -> None:
        """Upsert an Entra ID Directory Role as a Group node with EntraRole label."""
        meta = data.get("metadata", {})
        uid  = f"entraid:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (g:Group {uid: $uid})
                SET   g:EntraRole, g:DirectoryRole,
                      g.platform        = 'entraid',
                      g.platform_id     = $platform_id,
                      g.name            = $name,
                      g.display_name    = $name,
                      g.caption         = $name,
                      g.description     = $description,
                      g.entity_subtype  = 'role',
                      g.is_privileged   = $is_privileged,
                      g.is_enabled      = $is_enabled,
                      g.template_id     = $template_id,
                      g.updated_at      = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                name=data.get("name", ""),
                description=data.get("description"),
                is_privileged=meta.get("is_privileged", False),
                is_enabled=meta.get("is_enabled", True),
                template_id=meta.get("template_id"),
            )

    def upsert_entraid_group(self, data: dict[str, Any]) -> None:
        """Upsert an Entra ID M365/Security Group node."""
        meta = data.get("metadata", {})
        uid  = f"entraid:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (g:Group {uid: $uid})
                SET   g:EntraGroup,
                      g.platform        = 'entraid',
                      g.platform_id     = $platform_id,
                      g.name            = $name,
                      g.caption         = $name,
                      g.description     = $description,
                      g.entity_subtype  = 'security_group',
                      g.group_type      = $group_type,
                      g.membership_rule = $membership_rule,
                      g.updated_at      = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                name=data.get("name", ""),
                description=data.get("description"),
                group_type=meta.get("group_type", "Security"),
                membership_rule=meta.get("membership_rule"),
            )

    def upsert_entraid_ca_policy(self, data: dict[str, Any]) -> None:
        """Upsert a Conditional Access Policy as an Application node."""
        meta = data.get("metadata", {})
        uid  = f"entraid:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (a:Application {uid: $uid})
                SET   a:EntraPolicy,
                      a.platform              = 'entraid',
                      a.platform_id           = $platform_id,
                      a.name                  = $name,
                      a.entity_subtype        = 'ca_policy',
                      a.is_enabled            = $is_enabled,
                      a.state                 = $state,
                      a.conditions            = $conditions,
                      a.sign_in_risk_levels   = $sign_in_risk_levels,
                      a.user_risk_levels      = $user_risk_levels,
                      a.grant_controls        = $grant_controls,
                      a.targets_all_users     = $targets_all,
                      a.updated_at            = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                name=data.get("name", ""),
                is_enabled=meta.get("is_enabled", False),
                state=meta.get("state"),
                conditions=meta.get("conditions", []),
                sign_in_risk_levels=meta.get("sign_in_risk_levels", []),
                user_risk_levels=meta.get("user_risk_levels", []),
                grant_controls=meta.get("grant_controls", []),
                targets_all=meta.get("targets_all_users", False),
            )

    def upsert_entraid_app_registration(self, data: dict[str, Any]) -> None:
        """Upsert an Entra ID App Registration."""
        meta = data.get("metadata", {})
        uid  = f"entraid:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (a:Application {uid: $uid})
                SET   a:EntraApp,
                      a.platform             = 'entraid',
                      a.platform_id          = $platform_id,
                      a.name                 = $name,
                      a.entity_subtype       = 'app_registration',
                      a.app_id               = $app_id,
                      a.publisher_domain     = $publisher_domain,
                      a.publisher_verified   = $publisher_verified,
                      a.sign_in_audience     = $sign_in_audience,
                      a.created_date         = $created_date,
                      a.updated_at           = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                name=data.get("name", ""),
                app_id=meta.get("app_id"),
                publisher_domain=meta.get("publisher_domain"),
                publisher_verified=meta.get("publisher_verified", False),
                sign_in_audience=meta.get("sign_in_audience"),
                created_date=meta.get("created_date"),
            )

    def upsert_entraid_service_principal(self, data: dict[str, Any]) -> None:
        """Upsert an Entra ID Service Principal."""
        meta = data.get("metadata", {})
        uid  = f"entraid:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (a:Application {uid: $uid})
                SET   a:EntraSP,
                      a.platform             = 'entraid',
                      a.platform_id          = $platform_id,
                      a.name                 = $name,
                      a.entity_subtype       = 'service_principal',
                      a.app_id               = $app_id,
                      a.publisher_name       = $publisher_name,
                      a.publisher_verified   = $publisher_verified,
                      a.sp_type              = $sp_type,
                      a.created_date         = $created_date,
                      a.enabled              = $enabled,
                      a.updated_at           = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                name=data.get("name", ""),
                app_id=meta.get("app_id"),
                publisher_name=meta.get("publisher_name"),
                publisher_verified=meta.get("publisher_verified", False),
                sp_type=meta.get("sp_type"),
                created_date=meta.get("created_date"),
                enabled=data.get("is_active", True),
            )

    def upsert_entraid_device(self, data: dict[str, Any]) -> None:
        """Upsert an Entra ID Device as a Resource node."""
        meta = data.get("metadata", {})
        uid  = f"entraid:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (r:Resource {uid: $uid})
                SET   r:EntraDevice,
                      r.platform                 = 'entraid',
                      r.platform_id              = $platform_id,
                      r.name                     = $name,
                      r.resource_subtype         = 'device',
                      r.resource_type            = 'device',
                      r.device_id                = $device_id,
                      r.operating_system         = $os,
                      r.os_version               = $os_version,
                      r.is_compliant             = $is_compliant,
                      r.is_managed               = $is_managed,
                      r.trust_type               = $trust_type,
                      r.is_enabled               = $is_enabled,
                      r.last_sign_in_days_ago    = $last_sign_in_days,
                      r.registration_date        = $reg_date,
                      r.updated_at               = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                name=data.get("name", ""),
                device_id=meta.get("device_id"),
                os=meta.get("operating_system"),
                os_version=meta.get("os_version"),
                is_compliant=meta.get("is_compliant"),
                is_managed=meta.get("is_managed"),
                trust_type=meta.get("trust_type"),
                is_enabled=meta.get("is_enabled", True),
                last_sign_in_days=meta.get("last_sign_in_days_ago"),
                reg_date=meta.get("registration_date"),
            )

    def _link_entraid_role_membership(self, perm: dict[str, Any]) -> None:
        """
        Create HAS_ROLE (User/SP → DirectoryRole) edge for Entra ID.
        Uses label-free MATCH so it works for both User and Application nodes.
        Relationship type HAS_ROLE matches the Cypher detection rules in the rules engine.
        """
        grantee_uid = f"entraid:{perm['grantee_id']}"
        role_uid    = f"entraid:{perm['resource_id']}"
        with self._session() as session:
            result = session.run(
                """
                OPTIONAL MATCH (principal {uid: $grantee_uid})
                WITH principal WHERE principal IS NOT NULL
                MATCH (role:Group {uid: $role_uid})
                MERGE (principal)-[rel:HAS_ROLE]->(role)
                SET rel.assignment_type = $assignment_type,
                    rel.assigned_date   = $assigned_date,
                    rel.updated_at      = timestamp()
                RETURN count(*) AS matched
                """,
                grantee_uid=grantee_uid,
                role_uid=role_uid,
                assignment_type=perm.get("assignment_type", "active"),
                assigned_date=perm.get("assigned_date"),
            )
            row = result.single()
            if row and row["matched"] == 0:
                log.debug(
                    "role_link_missed",
                    extra={"grantee_uid": grantee_uid, "role_uid": role_uid},
                )

    def create_federated_identities_by_email(self) -> int:
        """
        Create FEDERATED_IDENTITY edges between users on different platforms
        that share the same email address.

        Returns the number of new edges created.
        """
        with self._session() as session:
            result = session.run(
                """
                MATCH (u1:User {platform: 'entraid'})
                WHERE u1.email IS NOT NULL AND u1.email <> ''
                MATCH (u2:User)
                WHERE u2.platform <> 'entraid'
                  AND u2.email = u1.email
                MERGE (u1)-[r:FEDERATED_IDENTITY]-(u2)
                RETURN count(r) AS created
                """
            )
            row = result.single()
            count = row["created"] if row else 0
            log.info("federated_identities_created", extra={"count": count})
            return count

    def get_entraid_graph_stats(self) -> dict[str, int]:
        """Return node counts for the Entra ID subgraph."""
        with self._session() as session:
            result = session.run(
                """
                MATCH (u:EntraUser)   WITH count(u) AS users
                MATCH (g:EntraOrg)    WITH users, count(g) AS orgs
                OPTIONAL MATCH (r:EntraRole)   WITH users, orgs, count(r) AS roles
                OPTIONAL MATCH (p:EntraPolicy) WITH users, orgs, roles, count(p) AS policies
                OPTIONAL MATCH (a:EntraApp)    WITH users, orgs, roles, policies, count(a) AS apps
                OPTIONAL MATCH (s:EntraSP)     WITH users, orgs, roles, policies, apps, count(s) AS sps
                OPTIONAL MATCH (d:EntraDevice) WITH users, orgs, roles, policies, apps, sps, count(d) AS devices
                RETURN users, orgs, roles, policies, apps, sps, devices
                """
            )
            row = result.single()
            return dict(row) if row else {}

    # ── (end Entra ID upserts) ────────────────────────────────────────────────

    def upsert_user_jira(self, data: dict[str, Any]) -> None:
        """
        Upsert a Jira user — extends the base upsert_user with Jira-specific
        fields (account_type, email_domain, last_login_days_ago).
        """
        meta = data.get("metadata", {})
        uid = f"jira:{data['platform_id']}"
        with self._session() as session:
            session.run(
                """
                MERGE (u:User {uid: $uid})
                SET   u:JiraUser,
                      u.platform           = 'jira',
                      u.platform_id        = $platform_id,
                      u.username           = $username,
                      u.display_name       = $display_name,
                      u.email              = $email,
                      u.is_active          = $is_active,
                      u.is_external        = $is_external,
                      u.account_type       = $account_type,
                      u.email_domain       = $email_domain,
                      u.two_factor_enabled = $two_factor_enabled,
                      u.last_login_days_ago = $last_login_days_ago,
                      u.caption            = $caption,
                      u.updated_at         = timestamp()
                """,
                uid=uid,
                platform_id=data["platform_id"],
                username=data.get("username"),
                display_name=data.get("display_name"),
                email=data.get("email"),
                is_active=data.get("is_active", True),
                is_external=data.get("is_external", False),
                account_type=meta.get("account_type", "atlassian"),
                email_domain=meta.get("email_domain"),
                two_factor_enabled=meta.get("two_factor_enabled"),
                last_login_days_ago=meta.get("last_login_days_ago"),
                caption=data.get("display_name") or data.get("email") or data.get("platform_id", ""),
            )

    # ── Relationship upserts ──────────────────────────────────────────────────

    def link_user_to_org(self, platform: str, user_id: str, org_id: str, role: str = "member") -> None:
        user_uid = f"{platform}:{user_id}"
        org_uid  = f"{platform}:{org_id}"
        with self._session() as session:
            result = session.run(
                """
                MATCH (u:User {uid: $user_uid})
                MATCH (o:Org  {uid: $org_uid})
                MERGE (u)-[rel:MEMBER_OF]->(o)
                SET rel.role = $role, rel.updated_at = timestamp()
                RETURN count(*) AS matched
                """,
                user_uid=user_uid, org_uid=org_uid, role=role,
            )
            matched = result.single()["matched"]
            if matched == 0:
                log.warning("link_missed", extra={"rel": "User-MEMBER_OF-Org", "user_uid": user_uid, "org_uid": org_uid})

    def link_user_to_group(self, platform: str, user_id: str, group_id: str) -> None:
        user_uid  = f"{platform}:{user_id}"
        group_uid = f"{platform}:{group_id}"
        with self._session() as session:
            session.run(
                """
                MATCH (u:User  {uid: $user_uid})
                MATCH (g:Group {uid: $group_uid})
                MERGE (u)-[:MEMBER_OF]->(g)
                """,
                user_uid=user_uid, group_uid=group_uid,
            )

    def link_user_to_resource(
        self,
        platform: str,
        user_id: str,
        resource_id: str,
        role: str,
        perm_admin: bool = False,
        perm_maintain: bool = False,
        perm_push: bool = False,
        perm_triage: bool = False,
        perm_pull: bool = False,
        source: str = "explicit",
    ) -> None:
        user_uid     = f"{platform}:{user_id}"
        resource_uid = f"{platform}:{resource_id}"
        with self._session() as session:
            result = session.run(
                """
                MATCH (u:User     {uid: $user_uid})
                MATCH (r:Resource {uid: $resource_uid})
                MERGE (u)-[rel:HAS_ROLE]->(r)
                SET   rel.role         = $role,
                      rel.admin        = $perm_admin,
                      rel.maintain     = $perm_maintain,
                      rel.push         = $perm_push,
                      rel.triage       = $perm_triage,
                      rel.pull         = $perm_pull,
                      rel.source       = $source,
                      rel.updated_at   = timestamp()
                RETURN count(*) AS matched
                """,
                user_uid=user_uid, resource_uid=resource_uid, role=role,
                perm_admin=perm_admin, perm_maintain=perm_maintain,
                perm_push=perm_push, perm_triage=perm_triage, perm_pull=perm_pull,
                source=source,
            )
            matched = result.single()["matched"]
            if matched == 0:
                log.warning("link_missed", extra={"rel": "User-HAS_ROLE-Resource", "user_uid": user_uid, "resource_uid": resource_uid})

    def link_resource_to_org(self, platform: str, resource_id: str, org_id: str) -> None:
        resource_uid = f"{platform}:{resource_id}"
        org_uid      = f"{platform}:{org_id}"
        with self._session() as session:
            result = session.run(
                """
                MATCH (r:Resource {uid: $resource_uid})
                MATCH (o:Org      {uid: $org_uid})
                MERGE (r)-[:BELONGS_TO]->(o)
                RETURN count(*) AS matched
                """,
                resource_uid=resource_uid, org_uid=org_uid,
            )
            matched = result.single()["matched"]
            if matched == 0:
                log.warning("link_missed", extra={"rel": "Resource-BELONGS_TO-Org", "resource_uid": resource_uid, "org_uid": org_uid})

    # ── Batch import ──────────────────────────────────────────────────────────

    @staticmethod
    def _bucket(entities: list[dict[str, Any]]) -> dict[str, list[dict]]:
        """Split a flat entity list into a dict keyed by entity_type."""
        buckets: dict[str, list[dict]] = {
            "org": [], "user": [], "group": [], "resource": [],
            "permission": [], "application": [], "workflow": [],
        }
        for e in entities:
            et = e.get("entity_type", "")
            if et in buckets:
                buckets[et].append(e)
        return buckets

    def _upsert_orgs(self, orgs: list[dict], fallback_platform: str, fallback_org_id: str) -> str:
        """Upsert Org nodes. Returns the effective org_id to use for linking."""
        for o in orgs:
            meta = o.get("metadata", {})
            self.upsert_org(
                platform=o["platform"],
                org_id=o["platform_id"],
                name=o.get("name") or o["platform_id"],
                two_factor_required=meta.get("two_factor_required"),
                default_repo_permission=meta.get("default_repo_permission"),
                members_can_create_repos=meta.get("members_can_create_repos"),
            )
        if orgs:
            return orgs[0]["platform_id"]
        if fallback_org_id:
            self.upsert_org(platform=fallback_platform, org_id=fallback_org_id, name=fallback_org_id)
        return fallback_org_id

    def _link_to_org(self, platform: str, users: list[dict], resources: list[dict], org_id: str) -> None:
        """Create MEMBER_OF (User→Org) and BELONGS_TO (Resource→Org) edges."""
        for u in users:
            self.link_user_to_org(
                platform=platform,
                user_id=u["platform_id"],
                org_id=org_id,
                role=u.get("metadata", {}).get("github_role", "member"),
            )
        for r in resources:
            self.link_resource_to_org(platform=platform, resource_id=r["platform_id"], org_id=org_id)

    def _link_jira_group_members(self, groups: list[dict]) -> None:
        """Create MEMBER_OF (User→Group) edges from Jira group membership lists."""
        for g in groups:
            if g.get("is_organization"):
                continue
            group_id = g.get("platform_id", "")
            members: list[str] = g.get("metadata", {}).get("members", [])
            for account_id in members:
                self.link_user_to_group(platform="jira", user_id=account_id, group_id=group_id)

    def _link_permissions(self, permissions: list[dict]) -> None:
        """Route permission entities to the appropriate edge-creation helper."""
        for perm in permissions:
            resource_type = perm.get("resource_type")
            if resource_type == "role":
                self._link_entraid_role_membership(perm)
            elif resource_type == "group":
                self.link_user_to_group(
                    platform=perm["platform"],
                    user_id=perm["grantee_id"],
                    group_id=perm["resource_id"],
                )
            else:
                self.link_user_to_resource(
                    platform=perm["platform"],
                    user_id=perm["grantee_id"],
                    resource_id=perm["resource_id"],
                    role=perm["role"],
                    perm_admin=perm.get("perm_admin", False),
                    perm_maintain=perm.get("perm_maintain", False),
                    perm_push=perm.get("perm_push", False),
                    perm_triage=perm.get("perm_triage", False),
                    perm_pull=perm.get("perm_pull", False),
                    source=perm.get("source", "explicit"),
                )

    def _upsert_users(self, users: list[dict], platform: str) -> None:
        if platform == "jira":
            upsert_fn = self.upsert_user_jira
        elif platform == "salesforce":
            upsert_fn = self.upsert_salesforce_user
        elif platform == "entraid":
            upsert_fn = self.upsert_entraid_user
        else:
            upsert_fn = self.upsert_user
        for u in users:
            upsert_fn(u)

    def _upsert_group_item(self, g: dict) -> None:
        """Dispatch a single group entity to the right upsert method."""
        plat    = g.get("platform", "")
        is_org  = g.get("is_organization", False)
        subtype = g.get("metadata", {}).get("entity_subtype")

        if plat == "salesforce":
            if is_org:
                self.upsert_salesforce_org_group(g)
            elif subtype == "profile":
                self.upsert_salesforce_profile_group(g)
            else:
                self.upsert_group(g)
        elif plat == "entraid":
            if is_org:
                self.upsert_entraid_org(g)
            elif subtype == "role":
                self.upsert_entraid_role(g)
            else:
                self.upsert_entraid_group(g)
        elif is_org:
            self.upsert_jira_org_group(g)
        else:
            self.upsert_group(g)
            if plat == "jira":
                uid = f"jira:{g['platform_id']}"
                with self._session() as session:
                    session.run(
                        "MATCH (g:Group {uid: $uid}) SET g:JiraGroup, g.caption = g.name",
                        uid=uid,
                    )

    def _upsert_groups(self, groups: list[dict]) -> None:
        for g in groups:
            self._upsert_group_item(g)

    def _upsert_resources(self, resources: list[dict], platform: str) -> None:
        for r in resources:
            if platform == "jira" and r.get("resource_type") == "project":
                self.upsert_jira_project(r)
            elif platform == "entraid" and r.get("resource_subtype") == "device":
                self.upsert_entraid_device(r)
            else:
                self.upsert_resource(r)

    def _upsert_applications(self, applications: list[dict], platform: str) -> None:
        """Dispatch application entities to the right upsert method."""
        for a in applications:
            if platform == "salesforce":
                self.upsert_salesforce_app(a)
            elif platform == "entraid":
                self._upsert_entraid_application(a)
            else:
                self.upsert_application(a)

    def _upsert_entraid_application(self, a: dict) -> None:
        subtype = a.get("metadata", {}).get("entity_subtype", "")
        if subtype == "ca_policy":
            self.upsert_entraid_ca_policy(a)
        elif subtype == "app_registration":
            self.upsert_entraid_app_registration(a)
        elif subtype == "service_principal":
            self.upsert_entraid_service_principal(a)
        else:
            self.upsert_application(a)

    def import_entities(self, entities: list[dict[str, Any]], org_id: str = "") -> None:
        """Upsert all nodes then create all relationships."""
        b = self._bucket(entities)
        platform = (b["user"] or b["resource"] or [{"platform": "github"}])[0]["platform"]

        log.info("neo4j_import_start", extra={k: len(v) for k, v in b.items()})

        # ── Nodes ─────────────────────────────────────────────────────────────
        effective_org_id = self._upsert_orgs(b["org"], platform, org_id)
        self._upsert_users(b["user"], platform)
        self._upsert_groups(b["group"])
        self._upsert_resources(b["resource"], platform)
        self._upsert_applications(b["application"], platform)
        for w in b["workflow"]:
            self.upsert_workflow(w)

        # ── Relationships ─────────────────────────────────────────────────────
        # Salesforce/Jira/Entra ID use Group node for org; GitHub uses Org node → link users
        if effective_org_id and platform not in ("jira", "salesforce", "entraid"):
            self._link_to_org(platform, b["user"], b["resource"], effective_org_id)
        if platform == "jira":
            self._link_jira_group_members(b["group"])
        self._link_permissions(b["permission"])

        log.info("neo4j_import_done", extra={"total": len(entities)})

    # ── Query helpers ─────────────────────────────────────────────────────────

    def get_all_nodes(self) -> list[dict[str, Any]]:
        with self._session() as session:
            return session.run("MATCH (n) RETURN n").data()

    def get_all_relationships(self) -> list[dict[str, Any]]:
        with self._session() as session:
            return session.run(
                "MATCH (a)-[r]->(b) RETURN a.uid AS from, type(r) AS rel, b.uid AS to, properties(r) AS props"
            ).data()

    def get_users_without_2fa(self, platform: str = "github") -> list[dict[str, Any]]:
        with self._session() as session:
            return session.run(
                """
                MATCH (u:User {platform: $platform})
                WHERE u.two_factor = false OR u.two_factor IS NULL
                RETURN u.username AS username, u.email AS email, u.github_role AS role
                ORDER BY u.github_role DESC
                """,
                platform=platform,
            ).data()

    def get_unprotected_repos(self, platform: str = "github") -> list[dict[str, Any]]:
        with self._session() as session:
            return session.run(
                """
                MATCH (r:Resource {platform: $platform, resource_subtype: 'repository'})
                WHERE r.branch_protected = false
                RETURN r.name AS repo, r.is_public AS is_public, r.visibility AS visibility
                ORDER BY r.is_public DESC
                """,
                platform=platform,
            ).data()

    def clear_platform_data(self, platform: str) -> dict[str, int]:
        """
        Delete all nodes and relationships for a given platform.
        Useful for a clean re-sync. Returns counts of deleted items.
        """
        with self._session() as session:
            rel_result = session.run(
                "MATCH ()-[r {platform: $p}]-() DELETE r RETURN count(r) AS deleted",
                p=platform,
            )
            rels_deleted = rel_result.single()["deleted"]
            node_result = session.run(
                "MATCH (n {platform: $p}) DETACH DELETE n RETURN count(n) AS deleted",
                p=platform,
            )
            nodes_deleted = node_result.single()["deleted"]
        log.info("platform_data_cleared", extra={"platform": platform, "nodes": nodes_deleted, "rels": rels_deleted})
        return {"nodes_deleted": nodes_deleted, "relationships_deleted": rels_deleted}

    def get_jira_graph_stats(self) -> dict[str, int]:
        """Return node/relationship counts for the Jira subgraph."""
        with self._session() as session:
            result = session.run(
                """
                MATCH (u:JiraUser)   WITH count(u) AS users
                MATCH (p:JiraProject) WITH users, count(p) AS projects
                MATCH (g:JiraGroup)  WITH users, projects, count(g) AS groups
                OPTIONAL MATCH (a:Application {platform: 'jira'})
                WITH users, projects, groups, count(a) AS apps
                OPTIONAL MATCH ()-[r:HAS_ROLE {platform: 'jira'}]->()
                RETURN users, projects, groups, apps, count(r) AS role_assignments
                """
            )
            row = result.single()
            return dict(row) if row else {}

    def get_salesforce_graph_stats(self) -> dict[str, int]:
        """Return node/relationship counts for the Salesforce subgraph."""
        with self._session() as session:
            result = session.run(
                """
                MATCH (u:SalesforceUser)  WITH count(u) AS users
                MATCH (g:SalesforceOrg)   WITH users, count(g) AS orgs
                OPTIONAL MATCH (p:SalesforceProfile) WITH users, orgs, count(p) AS profiles
                OPTIONAL MATCH (a:SalesforceApp)     WITH users, orgs, profiles, count(a) AS apps
                RETURN users, orgs, profiles, apps
                """
            )
            row = result.single()
            return dict(row) if row else {}

    def get_admin_users(self, platform: str = "github") -> list[dict[str, Any]]:
        with self._session() as session:
            return session.run(
                """
                MATCH (u:User {platform: $platform})-[r:HAS_ROLE {role: 'admin'}]->(res:Resource)
                RETURN u.username AS username, res.name AS resource, r.role AS role
                ORDER BY u.username
                """,
                platform=platform,
            ).data()
