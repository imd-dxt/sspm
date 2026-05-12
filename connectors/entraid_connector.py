"""
Microsoft Entra ID (Azure Active Directory) connector for SSPM.

Fetches:
  - Users (with sign-in activity)
  - MFA registration status per user
  - Groups and group memberships
  - Directory roles and role members (two-step via /directoryRoles)
  - App registrations and service principals
  - Conditional Access policies
  - Organization settings, Security Defaults, Authorization Policy
  - Devices

Authentication:
  OAuth 2.0 Client Credentials Flow.
  credentials dict must contain: client_id, client_secret
  tenant_id must be present in credentials OR config

Required Microsoft Graph API permissions (Application):
  User.Read.All, Directory.Read.All, Policy.Read.All,
  AuditLog.Read.All, Group.Read.All, Application.Read.All,
  Organization.Read.All, RoleManagement.Read.Directory,
  UserAuthenticationMethod.Read.All, Device.Read.All

Rate limits:
  Microsoft Graph: 10 000 req/10 min per app per tenant (~16 rps)
  Conservative default: 10 rps  (handled by RateLimitedSession)
  HTTP 429 + Retry-After: handled transparently by RateLimitedSession
"""
import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

from connectors.base_connector import (
    AuthError,
    BaseConnector,
    NetworkError,
    ParseError,
    SyncProgress,
)
from core.normalization import apply_canonical_attributes
from utils.http_client import RateLimitedSession

log = logging.getLogger(__name__)

_GRAPH_BASE  = "https://graph.microsoft.com/v1.0"
_LOGIN_BASE  = "https://login.microsoftonline.com"
_TOKEN_TTL   = 3500  # seconds — refresh a little before the 3600s expiry

# Privileged role template IDs (Microsoft-defined, tenant-independent)
_PRIVILEGED_TEMPLATE_IDS: frozenset[str] = frozenset({
    "62e90394-69f5-4237-9190-012177145e10",  # Global Administrator
    "194ae4cb-b126-40b2-bd5b-6091b380977d",  # Security Administrator
    "e8611ab8-c189-46e8-94e1-60213ab1f814",  # Privileged Role Administrator
    "fe930be7-5e62-47db-91af-98c3a49a38b1",  # User Administrator
    "9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3",  # Application Administrator
    "158c047a-c907-4556-b7ef-446551a6b5f7",  # Cloud Application Administrator
    "7be44c8a-adaf-4e2a-84d6-ab2649e08a13",  # Privileged Authentication Administrator
})

_SEL        = "$select"
_UTC_OFFSET = "+00:00"


class EntraIDConnector(BaseConnector):
    """Microsoft Entra ID (Azure AD) connector."""

    platform_name = "entraid"

    def __init__(self, credentials: dict[str, str], config: dict[str, Any] | None = None):
        super().__init__(credentials, config)
        self._tenant_id     = credentials.get("tenant_id") or (config or {}).get("tenant_id", "")
        self._client_id     = credentials.get("client_id", "")
        self._client_secret = credentials.get("client_secret", "")

        self._access_token: str  = ""
        self._token_expiry: float = 0.0

        self._http = RateLimitedSession(
            rate_limit_rps=10.0,
            max_retries=3,
            timeout=60,
        )

    # ── Authentication ────────────────────────────────────────────────────────

    def authenticate(self) -> bool:
        """Exchange client credentials for a Graph API bearer token."""
        url = f"{_LOGIN_BASE}/{self._tenant_id}/oauth2/v2.0/token"
        payload = {
            "grant_type":    "client_credentials",
            "client_id":     self._client_id,
            "client_secret": self._client_secret,
            "scope":         "https://graph.microsoft.com/.default",
        }
        try:
            resp = requests.post(url, data=payload, timeout=30)
            if resp.status_code in (400, 401):
                body = resp.json()
                raise AuthError(
                    f"Entra ID auth failed: {body.get('error_description', body.get('error', str(body)))}"
                )
            resp.raise_for_status()
            data             = resp.json()
            self._access_token = data["access_token"]
            expires_in       = int(data.get("expires_in", 3600))
            self._token_expiry = time.time() + min(expires_in, _TOKEN_TTL)
            self._http.update_headers({
                "Authorization": f"Bearer {self._access_token}",
                "Accept":        "application/json",
                "Content-Type":  "application/json",
            })
            self._log.info("entraid_authenticated", extra={"tenant": self._tenant_id})
            return True
        except AuthError:
            raise
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (401, 403):
                raise AuthError("Entra ID credentials invalid or insufficient permissions.") from exc
            raise NetworkError(str(exc)) from exc
        except Exception as exc:
            raise NetworkError(str(exc)) from exc

    def _ensure_auth(self) -> None:
        """Re-authenticate when the cached token has expired."""
        if time.time() < self._token_expiry:
            return
        self.authenticate()

    def test_connection(self) -> dict[str, Any]:
        try:
            self.authenticate()
            orgs = self._paginate("/organization", {_SEL: "id,displayName", "$top": "1"})
            tenant = orgs[0] if orgs else {}
            return {
                "ok":          True,
                "platform":    "entraid",
                "identity":    self._client_id,
                "tenant_id":   self._tenant_id,
                "tenant_name": tenant.get("displayName", ""),
            }
        except Exception as exc:
            return {"ok": False, "platform": "entraid", "error": str(exc)}

    # ── Graph API pagination ──────────────────────────────────────────────────

    def _paginate(self, endpoint: str, params: dict | None = None) -> list[dict[str, Any]]:
        """
        GET all pages from a Graph API collection endpoint.
        Follows @odata.nextLink automatically.
        Caller supplies params including $top if the endpoint supports it.
        """
        items: list[dict[str, Any]] = []
        url: str | None = f"{_GRAPH_BASE}{endpoint}"
        req_params: dict | None = dict(params or {})

        while url:
            data       = self._http.get(url, params=req_params)
            req_params = None          # nextLink already encodes all params
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")

        return items

    def _get_singleton(self, endpoint: str, params: dict | None = None) -> dict[str, Any]:
        """GET a singleton resource (not a collection). Returns {} on 403/404."""
        try:
            result = self._http.get(f"{_GRAPH_BASE}{endpoint}", params=params)
            return result if isinstance(result, dict) else {}
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (403, 404):
                self._log.warning("graph_singleton_unavailable", extra={"endpoint": endpoint})
                return {}
            raise
        except Exception as exc:
            self._log.warning("graph_singleton_failed", extra={"endpoint": endpoint, "error": str(exc)})
            return {}

    def _safe_paginate(self, endpoint: str, params: dict | None = None) -> list[dict[str, Any]]:
        """_paginate that returns [] on 403/404 (premium API unavailable)."""
        try:
            return self._paginate(endpoint, params)
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (403, 404):
                self._log.warning("graph_unavailable", extra={"endpoint": endpoint, "status": code})
                return []
            raise
        except Exception as exc:
            self._log.warning("graph_failed", extra={"endpoint": endpoint, "error": str(exc)})
            return []

    # ── Fetch methods ─────────────────────────────────────────────────────────

    def fetch_users(self) -> list[dict[str, Any]]:
        """GET /users — basic profile + sign-in activity."""
        self._ensure_auth()
        select = (
            "id,displayName,userPrincipalName,mail,accountEnabled,"
            "userType,createdDateTime,onPremisesSyncEnabled,department,jobTitle,"
            "lastPasswordChangeDateTime,passwordPolicies,signInActivity"
        )
        return self._safe_paginate("/users", {"$top": "999", _SEL: select})

    def fetch_mfa_status(self) -> list[dict[str, Any]]:
        """
        GET /reports/authenticationMethods/userRegistrationDetails
        Requires UserAuthenticationMethod.Read.All. Returns [] on 403.
        """
        self._ensure_auth()
        return self._safe_paginate(
            "/reports/authenticationMethods/userRegistrationDetails",
            {"$top": "999"},
        )

    def fetch_groups(self) -> list[dict[str, Any]]:
        """GET /groups — M365 and security groups."""
        self._ensure_auth()
        select = (
            "id,displayName,groupTypes,securityEnabled,"
            "mailEnabled,membershipRule,createdDateTime,description"
        )
        return self._safe_paginate("/groups", {"$top": "999", _SEL: select})

    def fetch_group_members(self, group_id: str) -> list[dict[str, Any]]:
        """
        GET /groups/{group_id}/members — max $top=100 for this endpoint.
        @odata.type must NOT be in $select (causes 400).
        """
        self._ensure_auth()
        return self._safe_paginate(
            f"/groups/{group_id}/members",
            {"$top": "100", _SEL: "id,displayName,userPrincipalName"},
        )

    def fetch_directory_roles(self) -> list[dict[str, Any]]:
        """
        Two-step role fetch:
          Step 1: GET /directoryRoles  — active/assigned roles only.
                  Does NOT support $top (returns all in one page).
          Step 2: GET /directoryRoles/{id}/members  — per-role members.
                  Does NOT support $top (causes 400).
        Returns combined list of role dicts, each with a 'members' key.
        """
        self._ensure_auth()

        # Step 1 — no $top (endpoint rejects it)
        roles = self._safe_paginate(
            "/directoryRoles",
            {_SEL: "id,displayName,description,roleTemplateId"},
        )

        for role in roles:
            role_id = role.get("id", "")
            if not role_id:
                role["members"] = []
                continue
            # Step 2 — also no $top (causes 400 on this endpoint too)
            members = self._safe_paginate(
                f"/directoryRoles/{role_id}/members",
                {_SEL: "id,displayName,userPrincipalName"},
            )
            role["members"] = members

        return roles

    def fetch_applications(self) -> list[dict[str, Any]]:
        """GET /applications — app registrations with secrets/keys metadata."""
        self._ensure_auth()
        select = (
            "id,appId,displayName,createdDateTime,"
            "passwordCredentials,keyCredentials,requiredResourceAccess,signInAudience"
        )
        return self._safe_paginate("/applications", {"$top": "999", _SEL: select})

    def fetch_service_principals(self) -> list[dict[str, Any]]:
        """GET /servicePrincipals — enterprise applications."""
        self._ensure_auth()
        select = (
            "id,appId,displayName,accountEnabled,"
            "publisherName,verifiedPublisher,appRoles"
        )
        return self._safe_paginate("/servicePrincipals", {"$top": "999", _SEL: select})

    def fetch_conditional_access_policies(self) -> list[dict[str, Any]]:
        """
        GET /identity/conditionalAccess/policies
        Requires Policy.Read.All. Returns [] on 403 (no P1/P2).
        """
        self._ensure_auth()
        select = "id,displayName,state,conditions,grantControls,createdDateTime"
        return self._safe_paginate(
            "/identity/conditionalAccess/policies",
            {"$top": "100", _SEL: select},
        )

    def fetch_organization(self) -> dict[str, Any]:
        """GET /organization — tenant-level settings."""
        self._ensure_auth()
        select = (
            "id,displayName,onPremisesSyncEnabled,"
            "passwordNotificationWindowInDays,passwordValidityPeriodInDays"
        )
        results = self._safe_paginate("/organization", {"$top": "1", _SEL: select})
        return results[0] if results else {}

    def fetch_security_defaults(self) -> dict[str, Any]:
        """GET /policies/identitySecurityDefaultsEnforcementPolicy"""
        self._ensure_auth()
        return self._get_singleton("/policies/identitySecurityDefaultsEnforcementPolicy")

    def fetch_authorization_policy(self) -> dict[str, Any]:
        """GET /policies/authorizationPolicy — guest/consent/device settings."""
        self._ensure_auth()
        return self._get_singleton("/policies/authorizationPolicy")

    def fetch_devices(self) -> list[dict[str, Any]]:
        """GET /devices — registered and joined devices."""
        self._ensure_auth()
        select = (
            "id,displayName,operatingSystem,operatingSystemVersion,"
            "isCompliant,isManaged,approximateLastSignInDateTime,"
            "trustType,deviceId,accountEnabled"
        )
        return self._safe_paginate("/devices", {"$top": "999", _SEL: select})

    def fetch_permissions(self) -> list[dict[str, Any]]:
        # Permissions are assembled in sync() from roles + group members.
        return []

    def fetch_resources(self) -> list[dict[str, Any]]:
        # Devices are assembled in sync() via fetch_devices().
        return []

    # ── Normalization ─────────────────────────────────────────────────────────

    def normalize_data(self, raw: dict[str, Any], entity_type: str) -> dict[str, Any]:
        """Dispatch raw Graph API dict to the per-type normalizer."""
        dispatch = {
            "user":               self._norm_user,
            "group":              self._norm_group,
            "role":               self._norm_role,
            "application":        self._norm_application,
            "service_principal":  self._norm_service_principal,
            "ca_policy":          self._norm_ca_policy,
            "organization":       self._norm_organization,
            "device":             self._norm_device,
        }
        fn = dispatch.get(entity_type)
        if fn is None:
            raise ParseError(f"Unknown entity_type: {entity_type!r}")
        result = fn(raw)
        return apply_canonical_attributes(result, entity_type, "entraid")

    @staticmethod
    def _days_since(iso_str: str | None) -> int | None:
        if not iso_str:
            return None
        try:
            ts = datetime.fromisoformat(iso_str.replace("Z", _UTC_OFFSET))
            return (datetime.now(timezone.utc) - ts).days
        except Exception:
            return None

    @staticmethod
    def _norm_user(raw: dict[str, Any]) -> dict[str, Any]:
        uid  = raw.get("id", "")
        upn  = raw.get("userPrincipalName", uid)
        mail = raw.get("mail") or upn
        return {
            "entity_type":  "user",
            "platform":     "entraid",
            "platform_id":  uid,
            "email":        mail.lower() if mail else None,
            "username":     upn,
            "display_name": raw.get("displayName"),
            "is_active":    raw.get("accountEnabled", True),
            "is_external":  raw.get("userType", "Member") == "Guest",
            "metadata": {
                "user_type":               raw.get("userType", "Member"),
                "on_premises_sync_enabled": raw.get("onPremisesSyncEnabled", False),
                "department":              raw.get("department"),
                "job_title":               raw.get("jobTitle"),
                "created_date":            raw.get("createdDateTime"),
                "password_policies":       raw.get("passwordPolicies"),
                "last_sign_in_date":       (raw.get("signInActivity") or {}).get("lastSignInDateTime"),
                # Filled in during sync() after fetch_mfa_status()
                "mfa_registered": False,
                "mfa_methods":    [],
                "mfa_capable":    False,
                # Filled in during sync() after fetch_directory_roles()
                "assigned_roles": [],
                "is_privileged":  False,
                "risk_level":     "none",
                # Extra fields for rules
                "account_enabled": raw.get("accountEnabled", True),
                "sign_in_blocked": not raw.get("accountEnabled", True),
                "account_type": (
                    "ServiceAccount"
                    if (not raw.get("mail") and "#EXT#" not in upn and raw.get("userType") == "Member")
                    else "UserAccount"
                ),
                "is_break_glass": any(
                    kw in upn.lower()
                    for kw in ("breakglass", "break-glass", "breaker", "emergency")
                ),
            },
        }

    @staticmethod
    def _norm_group(raw: dict[str, Any]) -> dict[str, Any]:
        group_types = raw.get("groupTypes", [])
        is_dynamic  = "DynamicMembership" in group_types
        is_m365     = "Unified" in group_types
        if is_dynamic:
            group_type = "Dynamic"
        elif is_m365:
            group_type = "M365"
        else:
            group_type = "Security"
        return {
            "entity_type":     "group",
            "platform":        "entraid",
            "platform_id":     raw.get("id", ""),
            "name":            raw.get("displayName", ""),
            "description":     raw.get("description"),
            "is_organization": False,
            "metadata": {
                "entity_subtype":   "security_group",
                "group_type":       group_type,
                "is_security":      raw.get("securityEnabled", False),
                "is_dynamic":       is_dynamic,
                "mail_enabled":     raw.get("mailEnabled", False),
                "membership_rule":  raw.get("membershipRule"),
                "created_date":     raw.get("createdDateTime"),
            },
        }

    @staticmethod
    def _norm_role(raw: dict[str, Any]) -> dict[str, Any]:
        role_obj_id  = raw.get("id", "")
        template_id  = raw.get("roleTemplateId", "")
        is_priv      = template_id in _PRIVILEGED_TEMPLATE_IDS
        return {
            "entity_type":     "group",
            "platform":        "entraid",
            "platform_id":     role_obj_id,
            "name":            raw.get("displayName", ""),
            "description":     raw.get("description"),
            "is_organization": False,
            "metadata": {
                "entity_subtype": "role",
                "template_id":    template_id,
                "is_privileged":  is_priv,
                "is_built_in":    True,
            },
        }

    @staticmethod
    def _norm_application(raw: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        creds = raw.get("passwordCredentials", []) or []
        has_expiring = any(
            c.get("endDateTime") and
            (datetime.fromisoformat(c["endDateTime"].replace("Z", _UTC_OFFSET)) - now).days < 30
            for c in creds
            if c.get("endDateTime")
        )
        return {
            "entity_type": "application",
            "platform":    "entraid",
            "platform_id": raw.get("id", ""),
            "name":        raw.get("displayName", ""),
            "is_active":   True,
            "metadata": {
                "entity_subtype":      "app_registration",
                "app_id":              raw.get("appId"),
                "sign_in_audience":    raw.get("signInAudience"),
                "created_date":        raw.get("createdDateTime"),
                "has_expiring_secrets": has_expiring,
                "secret_count":        len(creds),
                "key_count":           len(raw.get("keyCredentials", []) or []),
            },
        }

    @staticmethod
    def _norm_service_principal(raw: dict[str, Any]) -> dict[str, Any]:
        vp = raw.get("verifiedPublisher") or {}
        return {
            "entity_type": "application",
            "platform":    "entraid",
            "platform_id": raw.get("id", ""),
            "name":        raw.get("displayName", ""),
            "is_active":   raw.get("accountEnabled", True),
            "metadata": {
                "entity_subtype":     "service_principal",
                "app_id":             raw.get("appId"),
                "publisher_name":     raw.get("publisherName"),
                "publisher_verified": bool(vp.get("displayName")),
            },
        }

    @staticmethod
    def _norm_ca_policy(raw: dict[str, Any]) -> dict[str, Any]:
        cond      = raw.get("conditions") or {}
        grant     = raw.get("grantControls") or {}
        cond_keys = ("signInRiskLevels", "userRiskLevels", "platforms", "locations", "clientAppTypes")
        return {
            "entity_type": "application",
            "platform":    "entraid",
            "platform_id": raw.get("id", ""),
            "name":        raw.get("displayName", ""),
            "is_active":   raw.get("state") == "enabled",
            "metadata": {
                "entity_subtype":      "ca_policy",
                "state":               raw.get("state"),
                "is_enabled":          raw.get("state") == "enabled",
                "conditions":          [k for k in cond_keys if cond.get(k)],
                "sign_in_risk_levels": cond.get("signInRiskLevels", []),
                "user_risk_levels":    cond.get("userRiskLevels", []),
                "grant_controls":      grant.get("builtInControls", []),
                "targets_all_users":   "All" in (cond.get("users") or {}).get("includeUsers", []),
            },
        }

    @staticmethod
    def _norm_organization(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "entity_type":     "group",
            "platform":        "entraid",
            "platform_id":     "org",
            "name":            raw.get("displayName", "Entra ID Tenant"),
            "is_organization": True,
            "metadata": {
                "entity_subtype":              "organization",
                "tenant_id":                   raw.get("id"),
                "tenant_name":                 raw.get("displayName"),
                "on_premises_sync_enabled":    raw.get("onPremisesSyncEnabled", False),
                "password_notification_days":  raw.get("passwordNotificationWindowInDays"),
                "password_validity_days":      raw.get("passwordValidityPeriodInDays"),
            },
        }

    def _norm_device(self, raw: dict[str, Any]) -> dict[str, Any]:
        last_seen = self._days_since(raw.get("approximateLastSignInDateTime"))
        return {
            "entity_type":      "resource",
            "platform":         "entraid",
            "platform_id":      raw.get("id", ""),
            "name":             raw.get("displayName", ""),
            "resource_subtype": "device",
            "is_public":        False,
            "metadata": {
                "entity_subtype":        "device",
                "device_id":             raw.get("deviceId"),
                "operating_system":      raw.get("operatingSystem"),
                "os_version":            raw.get("operatingSystemVersion"),
                "is_compliant":          raw.get("isCompliant"),
                "is_managed":            raw.get("isManaged"),
                "trust_type":            raw.get("trustType"),
                "is_enabled":            raw.get("accountEnabled", True),
                "last_sign_in_days_ago": last_seen,
            },
        }

    # ── Full sync ──────────────────────────────────────────────────────────────

    def _fetch_all_raw(self, progress: SyncProgress) -> dict[str, Any]:
        """Fetch every entity type from Graph API. Errors are recorded on progress."""
        result: dict[str, Any] = {
            "users": [], "mfa_map": {}, "groups": [], "roles": [],
            "apps": [], "sps": [], "ca_policies": [], "org": {}, "devices": [],
        }
        try:
            result["users"] = self.fetch_users()
            self._log.info("stage_done", extra={"stage": "users", "count": len(result["users"])})
        except Exception as exc:
            progress.record_error("users", str(exc))

        try:
            for row in self.fetch_mfa_status():
                result["mfa_map"][row.get("id", "")] = row
            self._log.info("stage_done", extra={"stage": "mfa_status", "count": len(result["mfa_map"])})
        except Exception as exc:
            progress.record_error("mfa_status", str(exc))

        try:
            result["groups"] = self.fetch_groups()
            self._log.info("stage_done", extra={"stage": "groups", "count": len(result["groups"])})
        except Exception as exc:
            progress.record_error("groups", str(exc))

        try:
            result["roles"] = self.fetch_directory_roles()
            self._log.info("stage_done", extra={"stage": "directory_roles", "count": len(result["roles"])})
        except Exception as exc:
            progress.record_error("directory_roles", str(exc))

        try:
            result["apps"] = self.fetch_applications()
            self._log.info("stage_done", extra={"stage": "applications", "count": len(result["apps"])})
        except Exception as exc:
            progress.record_error("applications", str(exc))

        try:
            result["sps"] = self.fetch_service_principals()
            self._log.info("stage_done", extra={"stage": "service_principals", "count": len(result["sps"])})
        except Exception as exc:
            progress.record_error("service_principals", str(exc))

        try:
            result["ca_policies"] = self.fetch_conditional_access_policies()
            self._log.info("stage_done", extra={"stage": "ca_policies", "count": len(result["ca_policies"])})
        except Exception as exc:
            progress.record_error("ca_policies", str(exc))

        try:
            org = self.fetch_organization()
            sec_def  = self.fetch_security_defaults()
            auth_pol = self.fetch_authorization_policy()
            org["_security_defaults"]    = sec_def
            org["_authorization_policy"] = auth_pol
            result["org"] = org
        except Exception as exc:
            progress.record_error("organization", str(exc))

        try:
            result["devices"] = self.fetch_devices()
            self._log.info("stage_done", extra={"stage": "devices", "count": len(result["devices"])})
        except Exception as exc:
            progress.record_error("devices", str(exc))

        return result

    @staticmethod
    def _build_role_maps(
        roles_raw: list[dict],
    ) -> tuple[dict[str, list[str]], dict[str, bool]]:
        """Build user_id → [role_names] and user_id → is_privileged maps."""
        user_roles: dict[str, list[str]] = {}
        user_is_privileged: dict[str, bool] = {}
        for role in roles_raw:
            template_id = role.get("roleTemplateId", "")
            is_priv     = template_id in _PRIVILEGED_TEMPLATE_IDS
            role_name   = role.get("displayName", "")
            for member in role.get("members", []):
                mid = member.get("id", "")
                if mid:
                    user_roles.setdefault(mid, []).append(role_name)
                    if is_priv:
                        user_is_privileged[mid] = True
        return user_roles, user_is_privileged

    def _normalize_users(
        self,
        users_raw: list[dict],
        mfa_map: dict[str, dict],
        user_roles: dict[str, list[str]],
        user_is_privileged: dict[str, bool],
    ) -> list[dict[str, Any]]:
        """Normalize users and enrich with MFA / role data."""
        entities: list[dict[str, Any]] = []
        for raw in users_raw:
            uid      = raw.get("id", "")
            mfa_info = mfa_map.get(uid, {})
            entity   = self.normalize_data(raw, "user")
            meta     = entity.get("metadata", {})
            meta["mfa_registered"] = mfa_info.get("isMfaRegistered", False)
            meta["mfa_capable"]    = mfa_info.get("isMfaCapable", False)
            meta["mfa_methods"]    = mfa_info.get("methodsRegistered", [])
            meta["mfa_enabled"]    = mfa_info.get("isMfaRegistered", False)
            meta["assigned_roles"] = user_roles.get(uid, [])
            meta["is_privileged"]  = user_is_privileged.get(uid, False)
            entities.append(entity)
        return entities

    def _normalize_groups(self, groups_raw: list[dict]) -> list[dict[str, Any]]:
        """Normalize groups and emit MEMBER_OF permission edges."""
        entities: list[dict[str, Any]] = []
        for raw in groups_raw:
            entities.append(self.normalize_data(raw, "group"))
            gid     = raw.get("id", "")
            members = self.fetch_group_members(gid) if gid else []
            for member in members:
                mid = member.get("id", "")
                if mid:
                    entities.append({
                        "entity_type":     "permission",
                        "platform":        "entraid",
                        "platform_id":     f"grp:{gid}:mem:{mid}",
                        "grantee_id":      mid,
                        "grantee_type":    "entraid_principal",
                        "resource_id":     gid,
                        "resource_type":   "group",
                        "role":            "member",
                        "assignment_type": "active",
                        "source":          "directory",
                    })
        return entities

    def _normalize_roles(self, roles_raw: list[dict]) -> list[dict[str, Any]]:
        """Normalize directory roles and emit HAS_ROLE permission edges."""
        entities: list[dict[str, Any]] = []
        for role in roles_raw:
            entities.append(self.normalize_data(role, "role"))
            role_id   = role.get("id", "")
            role_name = role.get("displayName", "")
            for member in role.get("members", []):
                mid = member.get("id", "")
                if mid and role_id:
                    entities.append({
                        "entity_type":     "permission",
                        "platform":        "entraid",
                        "platform_id":     f"role:{role_id}:mem:{mid}",
                        "grantee_id":      mid,
                        "grantee_type":    "entraid_principal",
                        "resource_id":     role_id,
                        "resource_type":   "role",
                        "role":            role_name,
                        "assignment_type": "active",
                        "source":          "directory",
                    })
        return entities

    def _normalize_apps_section(
        self,
        apps_raw: list[dict],
        sps_raw: list[dict],
        ca_policies_raw: list[dict],
        org_raw: dict,
        devices_raw: list[dict],
    ) -> list[dict[str, Any]]:
        """Normalize applications, service principals, CA policies, org, devices."""
        entities: list[dict[str, Any]] = []
        for raw in apps_raw:
            entities.append(self.normalize_data(raw, "application"))
        for raw in sps_raw:
            entities.append(self.normalize_data(raw, "service_principal"))
        for raw in ca_policies_raw:
            entities.append(self.normalize_data(raw, "ca_policy"))
        if org_raw.get("id"):
            entities.append(self.normalize_data(org_raw, "organization"))
        for raw in devices_raw:
            entities.append(self.normalize_data(raw, "device"))
        return entities

    def sync(self) -> SyncProgress:
        """
        Full sync:
          1. authenticate
          2. fetch all entity types
          3. enrich users with MFA status and role assignments
          4. normalize to canonical schema
          5. attach entities to SyncProgress for the caller to persist
        """
        progress = self._start_progress()

        try:
            self.authenticate()
        except AuthError as exc:
            progress.record_error("authenticate", str(exc))
            progress.finish()
            return progress

        raw = self._fetch_all_raw(progress)
        user_roles, user_is_privileged = self._build_role_maps(raw["roles"])

        entities: list[dict[str, Any]] = []
        entities += self._normalize_users(raw["users"], raw["mfa_map"], user_roles, user_is_privileged)
        entities += self._normalize_groups(raw["groups"])
        entities += self._normalize_roles(raw["roles"])
        entities += self._normalize_apps_section(
            raw["apps"], raw["sps"], raw["ca_policies"], raw["org"], raw["devices"]
        )

        progress.records_fetched = (
            len(raw["users"]) + len(raw["groups"]) + len(raw["roles"])
            + len(raw["apps"]) + len(raw["sps"]) + len(raw["ca_policies"])
            + len(raw["devices"]) + (1 if raw["org"].get("id") else 0)
        )
        progress.entities = entities  # type: ignore[attr-defined]
        self._finish_progress()
        return progress

    # ── Audit logs ─────────────────────────────────────────────────────────────

    def fetch_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        GET /auditLogs/directoryAudits — Entra ID directory audit log.
        Requires AuditLog.Read.All. Returns [] on 403.
        """
        try:
            self._ensure_auth()
            data    = self._http.get(
                f"{_GRAPH_BASE}/auditLogs/directoryAudits",
                params={"$top": limit, "$orderby": "activityDateTime desc"},
            )
            entries = data.get("value", []) if isinstance(data, dict) else []
        except Exception as exc:
            log.warning("entraid_audit_log_error: %s", exc)
            return []

        result = []
        for e in entries:
            initiated = e.get("initiatedBy") or {}
            actor     = (
                (initiated.get("user") or {}).get("userPrincipalName")
                or (initiated.get("app") or {}).get("displayName")
            )
            targets   = e.get("targetResources") or []
            resource  = targets[0].get("displayName") if targets else None
            ts_raw    = e.get("activityDateTime")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", _UTC_OFFSET)) if ts_raw else None
            except Exception:
                ts = None
            result.append({
                "actor":     actor,
                "action":    e.get("activityDisplayName") or e.get("operationType", ""),
                "resource":  resource,
                "timestamp": ts,
                "raw":       e,
            })
        return result
