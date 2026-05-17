"""
Jira Cloud connector for SSPM.

Fetches:
  - Organization metadata (domain, user count, permission scheme count)
  - Users (account type, active status; 2FA/last-login not available in REST API)
  - Groups and group memberships (including jira-administrators)
  - Projects with permission schemes and issue security schemes
  - Project role assignments (user × project × role)
  - Installed Marketplace apps (requires admin token; 403 handled gracefully)
  - Workflows (basic metadata)

Authentication:
  credentials dict must contain "email" and "api_token" keys.
  config dict must contain "domain" (e.g. "mycompany.atlassian.net").

Rate limits:
  Jira Cloud: 120 req/min per token → 2.0 req/s (conservative default)

API limitations (Jira Cloud REST API v3):
  - 2FA enforcement status: requires Atlassian Admin API (admin.atlassian.com)
  - SSO configuration: requires Atlassian Admin API
  - Domain verification: requires Atlassian Admin API
  - Password policy details: requires Atlassian Admin API
  - Last login date: not exposed in standard REST API
  - Audit log settings: not exposed in standard REST API
  Rules depending on these fields will generate no findings until those
  APIs are integrated (planned Phase 3).
"""
import base64
import logging
from datetime import datetime, timezone
from typing import Any

import requests

from connectors.base_connector import (
    AuthError,
    BaseConnector,
    NetworkError,
    ParseError,
    RateLimitError,
    SyncProgress,
)
from utils.http_client import RateLimitedSession
from core.normalization import apply_canonical_attributes

log = logging.getLogger(__name__)

# Global admin groups whose members should be treated as Jira admins
_ADMIN_GROUPS = {"jira-administrators", "jira-system-administrators", "site-admins"}


class JiraConnector(BaseConnector):
    """Jira Cloud organisation connector."""

    platform_name = "jira"
    _API_BASE = "/rest/api/3"

    def __init__(self, credentials: dict[str, str], config: dict[str, Any] | None = None):
        super().__init__(credentials, config)
        self._email = credentials.get("email", "")
        self._token = credentials.get("api_token", "")
        self._domain = (config or {}).get("domain", "").rstrip("/")
        # org domain without subdomain used to classify external users
        self._org_domain = self._domain.split(".")[0] if self._domain else ""

        if not self._domain.startswith("https://"):
            base_url = f"https://{self._domain}"
        else:
            base_url = self._domain

        self._http = RateLimitedSession(
            rate_limit_rps=2.0,   # 120/min
            max_retries=3,
            timeout=30,
            base_url=base_url,
        )
        # Jira Cloud uses HTTP Basic auth: base64(email:api_token)
        raw = f"{self._email}:{self._token}"
        encoded = base64.b64encode(raw.encode()).decode()
        self._http.update_headers({
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Atlassian-Token": "no-check",
        })

    # ── Auth / connection ─────────────────────────────────────────────────────

    def authenticate(self) -> bool:
        try:
            data = self._http.get(f"{self._API_BASE}/myself")
            self._log.info("jira_authenticated", extra={"account_id": data.get("accountId")})
            return True
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (401, 403):
                raise AuthError(
                    "Jira credentials invalid or lack required permissions. "
                    "Ensure the API token belongs to a Jira admin."
                ) from exc
            raise NetworkError(str(exc)) from exc

    def test_connection(self) -> dict[str, Any]:
        try:
            me = self._http.get(f"{self._API_BASE}/myself")
            server = self._http.get(f"{self._API_BASE}/serverInfo")
            return {
                "ok": True,
                "platform": "jira",
                "identity": me.get("emailAddress") or me.get("displayName"),
                "account_id": me.get("accountId"),
                "domain": self._domain,
                "server_title": server.get("serverTitle"),
                "server_version": server.get("version"),
                "deployment_type": server.get("deploymentType", "Cloud"),
            }
        except Exception as exc:
            return {"ok": False, "platform": "jira", "error": str(exc)}

    # ── Pagination ────────────────────────────────────────────────────────────

    def _paginate_jira(
        self,
        path: str,
        params: dict | None = None,
        values_key: str = "values",
        max_results: int = 50,
    ) -> list[dict]:
        """
        Paginate Jira REST API endpoints using startAt / maxResults.

        Most endpoints return: {startAt, maxResults, total, values: [...]}
        Some (e.g. group members) return: {startAt, maxResults, total, values: {values: [...]}}
        """
        params = dict(params or {})
        params["maxResults"] = max_results
        params["startAt"] = 0
        results: list[dict] = []

        while True:
            data = self._http.get(path, params=params)

            if isinstance(data, list):
                # Some endpoints return a plain list (e.g. /rest/api/3/project)
                results.extend(data)
                break

            items = data.get(values_key, [])
            if isinstance(items, dict):
                # Nested values (group member endpoint)
                items = items.get("values", [])
            results.extend(items)

            total = data.get("total", len(results))
            params["startAt"] += len(items)
            if not items or params["startAt"] >= total:
                break

        return results

    def _safe_get(self, path: str, params: dict | None = None) -> dict[str, Any] | None:
        """GET that returns None on 403/404 instead of raising."""
        try:
            return self._http.get(path, params=params)
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (403, 404):
                self._log.debug("api_unavailable", extra={"path": path, "status": code})
                return None
            raise

    # ── Fetchers ──────────────────────────────────────────────────────────────

    def fetch_users(self) -> list[dict[str, Any]]:
        """Fetch all Jira users. Account type 'app' = service/bot accounts."""
        raw_users = self._paginate_jira(
            f"{self._API_BASE}/users/search",
            params={"includeInactiveUsers": "true"},
            values_key="values",
            max_results=50,
        )
        # /users/search returns a plain list, not paginated object — handle both
        if not raw_users:
            # fallback: some instances use a different path
            try:
                raw_users = self._http.get(
                    f"{self._API_BASE}/users/search",
                    params={"maxResults": 200, "startAt": 0},
                )
                if not isinstance(raw_users, list):
                    raw_users = raw_users.get("values", [])
            except Exception:
                raw_users = []

        users = []
        for u in raw_users:
            if u.get("accountType") in ("unknown", "app"):
                continue
            users.append(self.normalize_data(u, entity_type="user"))
        return users

    def fetch_groups(self) -> list[dict[str, Any]]:
        """Fetch all groups + their members. Also emit org metadata group."""
        raw_groups = self._paginate_jira(
            f"{self._API_BASE}/group/bulk",
            values_key="values",
            max_results=50,
        )

        # Count permission schemes for org metadata
        perm_schemes = self._safe_get(f"{self._API_BASE}/permissionscheme") or {}
        perm_scheme_count = len(perm_schemes.get("permissionSchemes", []))

        # Build org metadata group
        org_meta = self._build_org_group(perm_scheme_count)

        groups = [org_meta]
        for g in raw_groups:
            group_name = g.get("name", "")
            try:
                members_data = self._paginate_jira(
                    f"{self._API_BASE}/group/member",
                    params={"groupName": group_name, "includeInactiveUsers": "false"},
                    values_key="values",
                    max_results=50,
                )
                member_ids = [m["accountId"] for m in members_data if "accountId" in m]
            except Exception:
                member_ids = []

            groups.append(self.normalize_data(
                {**g, "members": member_ids},
                entity_type="group",
            ))
        return groups

    def _build_org_group(self, perm_scheme_count: int) -> dict[str, Any]:
        """
        Build the special organization-level Group node.

        Most org-level security settings (2FA, SSO, domain verification, password
        policy) are only accessible via the Atlassian Admin API and will be null
        here. Rules checking these properties will produce no findings until the
        Admin API connector is added.
        """
        config_data = self._safe_get(f"{self._API_BASE}/configuration") or {}
        return {
            "entity_type": "group",
            "platform": "jira",
            "platform_id": "org",
            "name": self._org_domain or "organization",
            "is_organization": True,
            "description": f"Organization: {self._domain}",
            "metadata": {
                "domain": self._domain,
                "total_users": None,           # filled later from user count
                "permission_schemes_count": perm_scheme_count,
                # The following require Atlassian Admin API — left null for MVP
                "two_factor_required": None,
                "sso_enabled": None,
                "domain_verified": None,
                "public_signup_enabled": None,
                "oauth_approval_required": None,
                "audit_log_retention_days": None,
                "audit_log_forwarding_enabled": None,
                "encryption_at_rest_enabled": None,
                "captcha_enabled": config_data.get("votingEnabled"),  # placeholder
                "smtp_tls_enabled": None,
                "smtp_server": None,
                "mobile_policy_enabled": None,
                "password_min_length": None,
                "password_complexity_required": None,
            },
        }

    def fetch_resources(self) -> list[dict[str, Any]]:
        """
        Fetch all Jira projects with permission and security scheme metadata.
        Also fetches workflows as a secondary resource type.
        """
        # Load all issue security schemes once (map schemeId → scheme)
        security_schemes: dict[str, dict] = {}
        sec_data = self._safe_get(f"{self._API_BASE}/issuesecurityschemes") or {}
        for s in sec_data.get("issueSecuritySchemes", []):
            security_schemes[str(s["id"])] = s

        raw_projects = self._paginate_jira(
            f"{self._API_BASE}/project/search",
            params={"expand": "description,lead,issueTypes,projectKeys"},
            values_key="values",
            max_results=50,
        )

        resources = []
        for p in raw_projects:
            key = p.get("key", "")
            perm_scheme = self._get_project_permission_scheme(key)
            sec_scheme_id = p.get("issueSecurityScheme", {}).get("id") if p.get("issueSecurityScheme") else None
            has_security_scheme = sec_scheme_id is not None or bool(p.get("issueSecurityScheme"))

            # Detect if project uses project roles (heuristic: has any actors in roles)
            uses_project_roles = self._project_uses_roles(key)

            resources.append(self.normalize_data(
                {
                    **p,
                    "permission_scheme": perm_scheme,
                    "security_scheme_id": sec_scheme_id,
                    "has_security_scheme": has_security_scheme,
                    "uses_project_roles": uses_project_roles,
                },
                entity_type="resource",
            ))

        # Also return workflows
        resources.extend(self._fetch_workflows())
        return resources

    def _get_project_permission_scheme(self, project_key: str) -> dict[str, Any]:
        """Fetch permission scheme for a project. Returns {} on error."""
        data = self._safe_get(f"{self._API_BASE}/project/{project_key}/permissionscheme") or {}
        return {
            "id": str(data.get("id", "")),
            "name": data.get("name", ""),
            "is_default": "Default" in data.get("name", ""),
        }

    def _project_uses_roles(self, project_key: str) -> bool:
        """Return True if the project has any actors assigned via project roles."""
        try:
            roles = self._http.get(f"{self._API_BASE}/project/{project_key}/role")
            if not isinstance(roles, dict):
                return False
            for role_url in roles.values():
                if isinstance(role_url, str):
                    # Quick check: just return True if any roles are configured
                    # (full role actor fetch happens in fetch_permissions)
                    return True
        except Exception:
            pass
        return False

    def _fetch_workflows(self) -> list[dict[str, Any]]:
        """Fetch workflow metadata."""
        workflows = []
        try:
            data = self._safe_get(f"{self._API_BASE}/workflow/search") or {}
            raw_workflows = data.get("values", [])
            for w in raw_workflows:
                workflows.append(self.normalize_data(w, entity_type="workflow"))
        except Exception as exc:
            self._log.warning("workflow_fetch_failed", extra={"error": str(exc)})
        return workflows

    def fetch_permissions(self) -> list[dict[str, Any]]:
        """
        Build project role assignments: for every project, fetch all roles,
        then for each role fetch actor lists (users + groups).
        Returns one permission record per (user, project, role).
        """
        raw_projects = self._paginate_jira(
            f"{self._API_BASE}/project/search",
            values_key="values",
            max_results=50,
        )
        # Pre-fetch role ID → name mapping
        role_id_map = self._fetch_role_definitions()

        permissions = []
        for project in raw_projects:
            key = project.get("key", "")
            project_id = str(project.get("id", key))
            try:
                roles = self._http.get(f"{self._API_BASE}/project/{key}/role")
            except Exception:
                continue
            if not isinstance(roles, dict):
                continue

            for role_name, role_url in roles.items():
                if not isinstance(role_url, str):
                    continue
                role_id = role_url.rstrip("/").split("/")[-1]

                try:
                    role_detail = self._http.get(
                        f"{self._API_BASE}/project/{key}/role/{role_id}"
                    )
                except Exception:
                    continue

                for actor in role_detail.get("actors", []):
                    actor_type = actor.get("type", "")
                    if actor_type == "atlassian-user-role-actor":
                        account_id = actor.get("actorUser", {}).get("accountId") or actor.get("name", "")
                        if account_id:
                            permissions.append(self.normalize_data(
                                {
                                    "subject_id": account_id,
                                    "subject_type": "user",
                                    "resource_id": project_id,
                                    "resource_key": key,
                                    "role": role_detail.get("name", role_name),
                                },
                                entity_type="permission",
                            ))
                    elif actor_type == "atlassian-group-role-actor":
                        # Group-level role — skip for now (graph already has group memberships)
                        pass

        return permissions

    def _fetch_role_definitions(self) -> dict[str, str]:
        """Return {role_id: role_name} from global role definitions."""
        try:
            data = self._http.get(f"{self._API_BASE}/role")
            if isinstance(data, list):
                return {str(r["id"]): r["name"] for r in data if "id" in r}
        except Exception:
            pass
        return {}

    def fetch_applications(self) -> list[dict[str, Any]]:
        """
        Fetch installed Marketplace apps plus app-type service accounts from user search.

        Marketplace addon fetch requires admin:atlassian-connect scope — handled gracefully on 403.
        App-type accounts (accountType=="app") are always fetched from the user search endpoint.
        """
        apps: list[dict[str, Any]] = []

        # Marketplace addons (requires elevated scope)
        data = self._safe_get("/rest/atlassian-connect/1/addons")
        if data is None:
            self._log.info("apps_api_unavailable", extra={
                "reason": "403 — token lacks admin:atlassian-connect scope"
            })
        else:
            for addon in data if isinstance(data, list) else data.get("addons", []):
                apps.append(self.normalize_data(addon, entity_type="application"))

        # App-type service accounts from user search
        try:
            raw_users = self._http.get(
                f"{self._API_BASE}/users/search",
                params={"maxResults": 200, "startAt": 0},
            )
            if not isinstance(raw_users, list):
                raw_users = raw_users.get("values", [])
            for u in raw_users:
                if u.get("accountType") == "app":
                    apps.append(self.normalize_data(u, entity_type="application"))
        except Exception as exc:
            self._log.warning("app_users_fetch_failed", extra={"error": str(exc)})

        return apps

    # ── Normalization ─────────────────────────────────────────────────────────

    def normalize_data(self, raw: dict[str, Any], entity_type: str) -> dict[str, Any]:
        """Map raw Jira API data to the canonical SSPM schema."""
        result = self._normalize_raw(raw, entity_type)
        return apply_canonical_attributes(result, entity_type, "jira")

    def _normalize_raw(self, raw: dict[str, Any], entity_type: str) -> dict[str, Any]:  # noqa: C901
        """Internal normalization — no attribute injection."""

        if entity_type == "user":
            account_id = raw.get("accountId", "")
            email = raw.get("emailAddress", "")
            # Classify external users by email domain
            email_domain = email.split("@")[-1].lower() if "@" in email else ""
            is_external = bool(email_domain) and not email_domain.startswith(
                self._org_domain.split(".")[0].lower()
            )
            return {
                "entity_type": "user",
                "platform": "jira",
                "platform_id": account_id,
                "email": email,
                "username": raw.get("displayName", account_id),
                "display_name": raw.get("displayName"),
                "is_active": raw.get("active", True),
                "is_external": is_external,
                "metadata": {
                    "account_type": raw.get("accountType", "atlassian"),
                    "account_status": "active" if raw.get("active") else "inactive",
                    "locale": raw.get("locale"),
                    "timezone": raw.get("timeZone"),
                    "email_domain": email_domain,
                    # Not available in REST API:
                    "two_factor_enabled": None,
                    "last_login_date": None,
                    "last_login_days_ago": None,
                },
            }

        if entity_type == "group":
            is_org = raw.get("is_organization", False)
            uid_part = "org" if is_org else (raw.get("groupId") or raw.get("name", ""))
            meta = raw.get("metadata", {})
            return {
                "entity_type": "group",
                "platform": "jira",
                "platform_id": uid_part,
                "name": raw.get("name", uid_part),
                "description": raw.get("description"),
                "is_organization": is_org,
                "member_count": len(raw.get("members", [])),
                "metadata": meta if is_org else {
                    "group_id": raw.get("groupId"),
                    "members": raw.get("members", []),
                },
            }

        if entity_type == "resource":
            proj_id = str(raw.get("id", raw.get("key", "")))
            perm = raw.get("permission_scheme", {})
            return {
                "entity_type": "resource",
                "platform": "jira",
                "platform_id": proj_id,
                "name": raw.get("name", ""),
                "resource_subtype": "project",
                "resource_type": "project",
                "is_public": not raw.get("isPrivate", False),
                "metadata": {
                    "key": raw.get("key"),
                    "project_type": raw.get("projectTypeKey"),
                    "style": raw.get("style"),
                    "description": raw.get("description", ""),
                    "lead": (raw.get("lead") or {}).get("accountId"),
                    "is_private": raw.get("isPrivate", False),
                    "permission_scheme_id": perm.get("id"),
                    "permission_scheme_name": perm.get("name"),
                    "default_permission_scheme": perm.get("is_default", False),
                    "browse_permission": None,  # would require deep permission scheme parse
                    "security_scheme_id": raw.get("security_scheme_id"),
                    "has_security_scheme": raw.get("has_security_scheme", False),
                    "uses_project_roles": raw.get("uses_project_roles", True),
                },
            }

        if entity_type == "workflow":
            return {
                "entity_type": "workflow",
                "platform": "jira",
                "platform_id": raw.get("id", {}).get("name", raw.get("name", "")),
                "name": raw.get("id", {}).get("name") or raw.get("name", ""),
                "metadata": {
                    "has_transition_restrictions": False,  # requires deep workflow parse
                    "projects": [],
                },
            }

        if entity_type == "permission":
            return {
                "entity_type": "permission",
                "platform": "jira",
                "platform_id": f"{raw.get('subject_id', '')}:{raw.get('resource_key', raw.get('resource_id', ''))}",
                "grantee_id": raw.get("subject_id", ""),
                "grantee_type": raw.get("subject_type", "user"),
                "resource_id": raw.get("resource_id", ""),
                "resource_name": raw.get("resource_key", ""),
                "role": raw.get("role", ""),
                "source": "explicit",
            }

        if entity_type == "application":
            # App-type service account (accountType=="app" from user search)
            if raw.get("accountType") == "app":
                account_id = raw.get("accountId", "")
                return {
                    "entity_type": "application",
                    "platform": "jira",
                    "platform_id": account_id,
                    "name": raw.get("displayName", account_id),
                    "is_active": raw.get("active", True),
                    "metadata": {
                        "key": account_id,
                        "vendor": None,
                        "version": None,
                        "scopes": [],
                        "installed_date": None,
                        "last_used_days_ago": None,
                        "description": raw.get("emailAddress", ""),
                        "account_type": "app",
                    },
                }

            # Marketplace addon
            key = raw.get("key", raw.get("name", ""))
            vendor = (raw.get("vendor") or {})
            scopes: list[str] = []
            for scope_obj in raw.get("scopes", []):
                if isinstance(scope_obj, str):
                    scopes.append(scope_obj.upper())
                elif isinstance(scope_obj, dict):
                    scopes.append(scope_obj.get("key", "").upper())

            return {
                "entity_type": "application",
                "platform": "jira",
                "platform_id": key,
                "name": raw.get("name", key),
                "is_active": raw.get("state") == "ENABLED" or raw.get("enabled", True),
                "metadata": {
                    "key": key,
                    "vendor": vendor.get("name") if isinstance(vendor, dict) else str(vendor),
                    "version": raw.get("version"),
                    "scopes": scopes,
                    "installed_date": raw.get("installedDate"),
                    "last_used_days_ago": None,
                    "description": raw.get("description"),
                },
            }

        raise ParseError(f"Unknown entity_type: {entity_type!r}")

    # ── Full sync ─────────────────────────────────────────────────────────────

    def sync(self) -> SyncProgress:
        """
        Full sync: authenticate → fetch users, groups, resources,
        permissions, applications.

        Returns populated SyncProgress. Does not persist to DB (caller's job).
        """
        progress = self._start_progress()

        try:
            self.authenticate()
        except AuthError as exc:
            progress.record_error("authenticate", str(exc))
            progress.finish()
            return progress

        entity_fetchers = [
            ("users", self.fetch_users),
            ("groups", self.fetch_groups),
            ("resources", self.fetch_resources),
            ("permissions", self.fetch_permissions),
            ("applications", self.fetch_applications),
        ]

        all_entities: list[dict[str, Any]] = []
        for stage, fetcher in entity_fetchers:
            try:
                self._log.info("fetching_stage", extra={"stage": stage})
                entities = fetcher()
                all_entities.extend(entities)
                progress.records_fetched += len(entities)
                self._log.info("stage_done", extra={"stage": stage, "count": len(entities)})
            except Exception as exc:
                progress.record_error(stage, str(exc))

        # Update org group total_users count now that we have users
        user_count = sum(1 for e in all_entities if e.get("entity_type") == "user")
        for e in all_entities:
            if e.get("entity_type") == "group" and e.get("is_organization"):
                e.setdefault("metadata", {})["total_users"] = user_count

        progress.entities = all_entities  # type: ignore[attr-defined]
        self._finish_progress()
        return progress
