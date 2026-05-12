"""
Salesforce connector for SSPM.

Fetches:
  - Organization metadata (org type, instance info, security settings)
  - Users (active/inactive, profile, role, last login, dangerous permissions)
  - Profiles (with login IP range counts for security analysis)
  - Connected Apps (OAuth scopes, IP restrictions)

Authentication:
  OAuth 2.0 Username-Password Flow.
  credentials dict must contain: username, password, security_token,
                                  client_id, client_secret
  config dict must contain: instance (e.g. "yourcompany.my.salesforce.com")
  Defaults to "login.salesforce.com" if instance not set.

Rate limits:
  Salesforce: 100 API calls/20 seconds per OAuth token → conservative 4 rps

API limitations (Salesforce REST API v59.0):
  - MFA enforcement status: requires Salesforce Shield / Identity verification
  - Password policy settings: requires Metadata API (SecuritySettings)
  - SSO configuration: requires Metadata API
  - Health Check score: not available via REST (Setup UI only)
  - Session timeout settings: requires Metadata API / Tooling API
  - Event Monitoring enabled: requires license + Tooling API
  - Transaction Security policies: requires Metadata API
  - Apex code analysis: requires static code scanning tool
  - Sandbox details: requires Sandbox API
  Rules depending on these fields will generate no findings until those
  APIs are integrated (planned Phase 4).
"""
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
from core.normalization import apply_canonical_attributes
from utils.http_client import RateLimitedSession

log = logging.getLogger(__name__)

_API_VERSION = "v59.0"


class SalesforceConnector(BaseConnector):
    """Salesforce org connector."""

    platform_name = "salesforce"

    def __init__(self, credentials: dict[str, str], config: dict[str, Any] | None = None):
        super().__init__(credentials, config)
        self._client_id     = credentials.get("client_id", "")
        self._client_secret = credentials.get("client_secret", "")
        self._username      = credentials.get("username", "")
        self._password      = credentials.get("password", "")
        self._security_token = credentials.get("security_token", "")
        raw_instance = (config or {}).get("instance", "login.salesforce.com").rstrip("/")
        # Strip any scheme the user may have included (we add https:// ourselves)
        for prefix in ("https://", "http://"):
            if raw_instance.startswith(prefix):
                raw_instance = raw_instance[len(prefix):]
                break
        self._instance = raw_instance

        # Computed after authenticate()
        self._access_token: str = ""
        self._instance_url: str = ""

        # Org domain for external user classification
        # e.g. "acme.my.salesforce.com" → "acme"
        parts = self._instance.split(".")
        self._org_domain = parts[0].lower() if parts else ""

        self._http = RateLimitedSession(
            rate_limit_rps=4.0,
            max_retries=3,
            timeout=30,
        )

    # ── Auth / connection ─────────────────────────────────────────────────────

    def authenticate(self) -> bool:
        """Exchange username+password+token for an OAuth access token."""
        login_url = (
            f"https://{self._instance}/services/oauth2/token"
            if self._instance != "login.salesforce.com"
            else "https://login.salesforce.com/services/oauth2/token"
        )
        payload = {
            "grant_type":    "password",
            "client_id":     self._client_id,
            "client_secret": self._client_secret,
            "username":      self._username,
            "password":      self._password + self._security_token,
        }
        try:
            resp = requests.post(login_url, data=payload, timeout=30)
            if resp.status_code == 400:
                body = resp.json()
                raise AuthError(
                    f"Salesforce auth failed: {body.get('error_description', body)}"
                )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._instance_url = data["instance_url"].rstrip("/")
            self._http.update_headers({
                "Authorization": f"Bearer {self._access_token}",
                "Accept":        "application/json",
            })
            self._log.info("sf_authenticated", extra={"instance": self._instance_url})
            return True
        except AuthError:
            raise
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (401, 403):
                raise AuthError("Salesforce credentials invalid or app not authorized.") from exc
            raise NetworkError(str(exc)) from exc
        except Exception as exc:
            raise NetworkError(str(exc)) from exc

    def test_connection(self) -> dict[str, Any]:
        try:
            self.authenticate()
            me = self._http.get(f"{self._instance_url}/services/data/{_API_VERSION}/sobjects/User/{self._username_to_id()}")
            return {
                "ok":             True,
                "platform":       "salesforce",
                "identity":       self._username,
                "instance_url":   self._instance_url,
                "api_version":    _API_VERSION,
            }
        except Exception as exc:
            return {"ok": False, "platform": "salesforce", "error": str(exc)}

    def _username_to_id(self) -> str:
        """Return the Salesforce Id of the authenticated user (best-effort)."""
        try:
            rows = self._soql(
                f"SELECT Id FROM User WHERE Username = '{self._username}' LIMIT 1"
            )
            if rows:
                return rows[0].get("Id", "")
        except Exception:
            pass
        return ""

    # ── SOQL pagination ───────────────────────────────────────────────────────

    def _soql(self, query: str) -> list[dict[str, Any]]:
        """
        Execute a SOQL query and return all records, following nextRecordsUrl.
        """
        url = f"{self._instance_url}/services/data/{_API_VERSION}/query"
        params = {"q": query}
        records: list[dict[str, Any]] = []

        while True:
            try:
                data = self._http.get(url, params=params)
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else 0
                if code == 400:
                    body = {}
                    try:
                        body = exc.response.json()
                    except Exception:
                        pass
                    msg = body[0].get("message", str(body)) if isinstance(body, list) else str(body)
                    self._log.warning("soql_error", extra={"query": query[:80], "error": msg})
                    return []
                raise

            batch = data.get("records", [])
            records.extend(batch)

            if data.get("done", True):
                break

            next_url = data.get("nextRecordsUrl", "")
            if not next_url:
                break
            # nextRecordsUrl is a path like /services/data/v59.0/query/01g...
            url = f"{self._instance_url}{next_url}"
            params = {}

        return records

    def _safe_soql(self, query: str) -> list[dict[str, Any]]:
        """SOQL that returns [] on any error."""
        try:
            return self._soql(query)
        except Exception as exc:
            self._log.debug("safe_soql_failed", extra={"error": str(exc)})
            return []

    # ── Fetchers ──────────────────────────────────────────────────────────────

    def fetch_users(self) -> list[dict[str, Any]]:
        """
        Fetch all non-guest users with profile, role, last login.
        Also fetches dangerous permission assignments and maps them to users.
        """
        users_raw = self._soql(
            "SELECT Id, Username, Name, FirstName, LastName, Email, "
            "IsActive, LastLoginDate, UserType, CreatedDate, "
            "Profile.Name, UserRole.Name "
            "FROM User "
            "WHERE UserType != 'Guest' "
            "ORDER BY Username"
        )

        # Fetch users with dangerous permissions (ViewAllData, ModifyAllData, AuthorApex)
        dangerous: dict[str, dict[str, bool]] = {}
        perm_rows = self._safe_soql(
            "SELECT AssigneeId, "
            "PermissionSet.PermissionsViewAllData, "
            "PermissionSet.PermissionsModifyAllData, "
            "PermissionSet.PermissionsAuthorApex "
            "FROM PermissionSetAssignment "
            "WHERE PermissionSet.PermissionsViewAllData = true "
            "   OR PermissionSet.PermissionsModifyAllData = true "
            "   OR PermissionSet.PermissionsAuthorApex = true"
        )
        for row in perm_rows:
            uid = row.get("AssigneeId", "")
            ps  = row.get("PermissionSet") or {}
            if not uid:
                continue
            existing = dangerous.get(uid, {})
            dangerous[uid] = {
                "has_view_all_data":   existing.get("has_view_all_data",   False) or ps.get("PermissionsViewAllData",   False),
                "has_modify_all_data": existing.get("has_modify_all_data", False) or ps.get("PermissionsModifyAllData", False),
                "has_author_apex":     existing.get("has_author_apex",     False) or ps.get("PermissionsAuthorApex",     False),
            }

        users = []
        for raw in users_raw:
            sf_id = raw.get("Id", "")
            perms = dangerous.get(sf_id, {})
            users.append(self.normalize_data({**raw, **perms}, entity_type="user"))
        return users

    def fetch_groups(self) -> list[dict[str, Any]]:
        """
        Fetch org metadata group + profiles.
        Profiles are fetched separately so login IP range data can be attached.
        """
        org_group = self._build_org_group()
        profiles  = self._fetch_profiles()
        return [org_group] + profiles

    def _build_org_group(self) -> dict[str, Any]:
        """
        Build the special organization-level Group node.

        Most security settings (MFA enforcement, password policy, SSO, Health Check)
        are only accessible via the Metadata API / Tooling API and will be null here.
        Rules checking these fields will produce no findings until those APIs are
        added (planned Phase 4).
        """
        org_rows = self._safe_soql(
            "SELECT Id, Name, InstanceName, OrganizationType, IsSandbox FROM Organization"
        )
        org_raw = org_rows[0] if org_rows else {}

        return {
            "entity_type":    "group",
            "platform":       "salesforce",
            "platform_id":    "org",
            "name":           org_raw.get("Name", self._org_domain or "Salesforce Org"),
            "is_organization": True,
            "description":    f"Salesforce org: {self._instance_url}",
            "metadata": {
                "org_id":            org_raw.get("Id"),
                "instance_name":     org_raw.get("InstanceName"),
                "org_type":          org_raw.get("OrganizationType"),
                "is_sandbox":        org_raw.get("IsSandbox", False),
                "instance_url":      self._instance_url,
                "total_users":       None,          # filled after user fetch
                # Settings not available in REST API — require Metadata / Tooling API
                "mfa_required":                  None,
                "password_min_length":           None,
                "password_complexity":           None,
                "password_history_restriction":  None,
                "password_max_age":              None,
                "sso_enabled":                   None,
                "health_check_score":            None,
                "session_timeout_minutes":       None,
                "event_monitoring_enabled":      None,
                "my_domain_deployed":            None,
                "version_control_enabled":       None,
                "audit_trail_siem_integration":  None,
                "login_forensics_enabled":       None,
                "scim_enabled":                  None,
                "identity_connect_enabled":      None,
            },
        }

    def _fetch_profiles(self) -> list[dict[str, Any]]:
        """Fetch profiles with login IP range info."""
        profiles_raw = self._safe_soql(
            "SELECT Id, Name, Description, UserLicense.Name FROM Profile ORDER BY Name"
        )

        # Build a set of profile IDs that have login IP restrictions
        ip_range_rows = self._safe_soql(
            "SELECT ProfileId FROM LoginIpRange"
        )
        profiles_with_ip = {row.get("ProfileId") for row in ip_range_rows if row.get("ProfileId")}

        profiles = []
        for raw in profiles_raw:
            profile_id = raw.get("Id", "")
            has_ip = profile_id in profiles_with_ip
            profiles.append(self.normalize_data(
                {**raw, "has_login_ip_ranges": has_ip},
                entity_type="profile",
            ))
        return profiles

    def fetch_resources(self) -> list[dict[str, Any]]:
        """Fetch Connected Apps as resource/application entities."""
        return []  # Connected apps returned via fetch_applications

    def fetch_permissions(self) -> list[dict[str, Any]]:
        """
        Build user→profile permission records.
        These create HAS_ROLE edges: User -[HAS_ROLE {role: profile_name}]-> Org
        so that profile-level queries can traverse the graph.
        """
        # For Salesforce, profile assignment is stored on the User node directly.
        # We return empty here; the user's profile name is stored as a property.
        return []

    def fetch_applications(self) -> list[dict[str, Any]]:
        """Fetch Connected Apps with OAuth scope and IP restriction data."""
        apps_raw = self._safe_soql(
            "SELECT Id, Name, ContactEmail, OptionsAllowAdminApprovedUsersOnly "
            "FROM ConnectedApplication ORDER BY Name"
        )
        if not apps_raw:
            return []

        apps = []
        for raw in apps_raw:
            apps.append(self.normalize_data(raw, entity_type="application"))
        return apps

    # ── Normalization ─────────────────────────────────────────────────────────

    def normalize_data(self, raw: dict[str, Any], entity_type: str) -> dict[str, Any]:
        """Map raw Salesforce API data to the canonical SSPM schema."""
        result = self._normalize_raw(raw, entity_type)
        return apply_canonical_attributes(result, entity_type, "salesforce")

    def _normalize_raw(self, raw: dict[str, Any], entity_type: str) -> dict[str, Any]:  # noqa: C901
        """Internal normalization — no attribute injection."""

        if entity_type == "user":
            sf_id    = raw.get("Id", "")
            email    = raw.get("Email", "")
            username = raw.get("Username", sf_id)

            email_domain = email.split("@")[-1].lower() if "@" in email else ""
            is_external  = bool(email_domain) and not email_domain.endswith("salesforce.com")

            # Calculate last-login days ago from ISO timestamp
            last_login_str = raw.get("LastLoginDate")
            last_login_days_ago: int | None = None
            if last_login_str:
                try:
                    ts = datetime.fromisoformat(last_login_str.replace("Z", "+00:00"))
                    last_login_days_ago = (datetime.now(timezone.utc) - ts).days
                except Exception:
                    pass

            user_type = raw.get("UserType", "Standard")
            profile   = (raw.get("Profile") or {}).get("Name") or raw.get("profile_name")
            role      = (raw.get("UserRole") or {}).get("Name")

            return {
                "entity_type":  "user",
                "platform":     "salesforce",
                "platform_id":  sf_id,
                "email":        email,
                "username":     username,
                "display_name": raw.get("Name"),
                "is_active":    raw.get("IsActive", True),
                "is_external":  is_external,
                "metadata": {
                    "profile":               profile,
                    "role":                  role,
                    "user_type":             user_type,
                    "last_login_days_ago":   last_login_days_ago,
                    "is_integration_user":   user_type in ("AutomatedProcess", "DatabaseUser"),
                    "has_view_all_data":     raw.get("has_view_all_data", False),
                    "has_modify_all_data":   raw.get("has_modify_all_data", False),
                    "has_author_apex":       raw.get("has_author_apex", False),
                    "mfa_enabled":           None,   # not available in REST API
                },
            }

        if entity_type == "profile":
            profile_id = raw.get("Id", raw.get("Name", ""))
            name       = raw.get("Name", "")
            return {
                "entity_type":    "group",
                "platform":       "salesforce",
                "platform_id":    f"profile:{profile_id}",
                "name":           name,
                "description":    raw.get("Description"),
                "is_organization": False,
                "member_count":   0,
                "metadata": {
                    "entity_subtype":      "profile",
                    "license":             (raw.get("UserLicense") or {}).get("Name"),
                    "has_login_ip_ranges": raw.get("has_login_ip_ranges", False),
                },
            }

        if entity_type == "group":
            # Org metadata group
            is_org = raw.get("is_organization", False)
            meta   = raw.get("metadata", {})
            uid    = "org" if is_org else (raw.get("platform_id", raw.get("name", "")))
            return {
                "entity_type":    "group",
                "platform":       "salesforce",
                "platform_id":    uid,
                "name":           raw.get("name", uid),
                "description":    raw.get("description"),
                "is_organization": is_org,
                "member_count":   0,
                "metadata":       meta,
            }

        if entity_type == "application":
            sf_id = raw.get("Id", raw.get("Name", ""))
            name  = raw.get("Name", sf_id)
            # ConnectedApplication object doesn't expose OAuth scopes via SOQL —
            # they're stored in metadata. We store what we can.
            return {
                "entity_type": "application",
                "platform":    "salesforce",
                "platform_id": sf_id,
                "name":        name,
                "is_active":   True,
                "metadata": {
                    "contact_email":           raw.get("ContactEmail"),
                    "admin_approved_only":      raw.get("OptionsAllowAdminApprovedUsersOnly", False),
                    # OAuth scopes and IP ranges not available via standard SOQL
                    "oauth_scopes":             [],
                    "has_ip_restrictions":      None,
                    "ip_ranges":                [],
                },
            }

        if entity_type == "permission":
            return {
                "entity_type":  "permission",
                "platform":     "salesforce",
                "platform_id":  f"{raw.get('grantee_id', '')}:{raw.get('resource_id', '')}",
                "grantee_id":   raw.get("grantee_id", ""),
                "grantee_type": "user",
                "resource_id":  raw.get("resource_id", ""),
                "resource_name": raw.get("resource_name", ""),
                "role":         raw.get("role", ""),
                "source":       "explicit",
            }

        raise ParseError(f"Unknown entity_type: {entity_type!r}")

    # ── Full sync ─────────────────────────────────────────────────────────────

    def sync(self) -> SyncProgress:
        """
        Full sync: authenticate → fetch users, groups (org+profiles),
        applications.

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
            ("users",        self.fetch_users),
            ("groups",       self.fetch_groups),
            ("resources",    self.fetch_resources),
            ("permissions",  self.fetch_permissions),
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

        # Patch org group with total user count
        user_count = sum(1 for e in all_entities if e.get("entity_type") == "user")
        for e in all_entities:
            if e.get("entity_type") == "group" and e.get("is_organization"):
                e.setdefault("metadata", {})["total_users"] = user_count

        progress.entities = all_entities  # type: ignore[attr-defined]
        self._finish_progress()
        return progress
