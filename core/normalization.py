"""
core/normalization.py — Canonical attributes normalizer.

Every connector must call `apply_canonical_attributes(data_json, entity_type, platform)`
before persisting a NormalizedEntity. This appends a top-level `attributes` dict with
unified field names so that condition-based rules (CIS-6, NIST-63, ISO 27001) can run
against any platform without per-platform field mapping in the rule itself.

The existing `metadata` sub-dict is preserved unchanged so that legacy Cypher rules
continue to work. We only ADD an `attributes` sibling.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Severity of the "is_privileged" heuristic — per-platform role names that
# indicate elevated privilege without formal admin assignment.
# ---------------------------------------------------------------------------

_PRIVILEGED_ROLES: frozenset[str] = frozenset({
    # GitHub
    "admin", "owner", "site-admin",
    # Jira
    "jira-administrators", "jira-system-administrators", "site-admins",
    # Salesforce
    "system administrator",
    # Entra
    "global administrator", "privileged role administrator",
    "security administrator", "privileged authentication administrator",
    # Generic
    "administrator", "superadmin", "super admin",
})


def _is_privileged_role(roles: list[str]) -> bool:
    return any(r.lower() in _PRIVILEGED_ROLES for r in roles)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _days_ago(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (now - dt).days)


# ---------------------------------------------------------------------------
# Per-platform extractors  →  canonical attributes dict
# ---------------------------------------------------------------------------

def _github_attributes(data_json: dict, entity_type: str) -> dict:
    meta = data_json.get("metadata") or {}
    attrs: dict[str, Any] = {}

    if entity_type == "user":
        attrs["mfa_enabled"] = meta.get("two_factor_enabled")
        attrs["is_active"] = data_json.get("is_active", True)
        role = meta.get("github_role", "member")
        attrs["roles"] = [role] if role else []
        attrs["is_privileged"] = role == "admin" or meta.get("site_admin", False)
        attrs["last_login_at"] = None  # GitHub REST API does not expose last login
        attrs["status"] = "active" if attrs["is_active"] else "inactive"
        attrs["is_external"] = data_json.get("is_external", False)
        attrs["source"] = "github"
        attrs["sso_enforced"] = None
        attrs["directory_managed"] = None
        attrs["terminated_user"] = False  # No termination concept in GitHub

    elif entity_type in ("org", "group"):
        attrs["mfa_required"] = meta.get("two_factor_required") or meta.get("two_factor_requirement_enabled")
        attrs["sso_enforced"] = None
        attrs["directory_managed"] = None
        attrs["externally_exposed"] = True  # GitHub orgs are internet-accessible

    return attrs


def _entraid_attributes(data_json: dict, entity_type: str) -> dict:
    meta = data_json.get("metadata") or {}
    attrs: dict[str, Any] = {}

    if entity_type == "user":
        attrs["mfa_enabled"] = meta.get("mfa_registered") or data_json.get("mfa_registered")
        attrs["is_active"] = data_json.get("is_active", meta.get("is_active", True))
        roles: list[str] = meta.get("roles") or data_json.get("roles") or []
        attrs["roles"] = roles
        attrs["is_privileged"] = meta.get("is_privileged", False) or _is_privileged_role(roles)

        # Last login
        last_signin = meta.get("last_sign_in_date") or meta.get("last_sign_in_at")
        dt = _parse_iso(last_signin)
        attrs["last_login_at"] = last_signin
        attrs["last_login_days_ago"] = _days_ago(dt)

        attrs["status"] = "active" if attrs["is_active"] else "inactive"
        attrs["is_external"] = meta.get("user_type") == "Guest"
        attrs["source"] = "directory" if meta.get("on_premises_sync_enabled") else "cloud"
        attrs["sso_enforced"] = None  # Not derivable per-user
        attrs["directory_managed"] = not meta.get("on_premises_sync_enabled", False)
        attrs["terminated_user"] = not attrs["is_active"]

    elif entity_type in ("org", "group"):
        attrs["mfa_required"] = meta.get("security_defaults_enabled") or meta.get("mfa_required")
        attrs["sso_enforced"] = meta.get("sso_enforced")
        attrs["directory_managed"] = True
        attrs["externally_exposed"] = True

    return attrs


def _salesforce_attributes(data_json: dict, entity_type: str) -> dict:
    meta = data_json.get("metadata") or {}
    attrs: dict[str, Any] = {}

    if entity_type == "user":
        attrs["mfa_enabled"] = None  # Not available via REST API
        is_active = data_json.get("is_active", meta.get("is_active", True))
        attrs["is_active"] = is_active
        profile = meta.get("profile") or data_json.get("profile", "")
        attrs["roles"] = [profile] if profile else []
        attrs["is_privileged"] = profile.lower() == "system administrator"

        last_login = meta.get("last_login_date") or meta.get("last_login_at")
        dt = _parse_iso(last_login)
        attrs["last_login_at"] = last_login
        attrs["last_login_days_ago"] = _days_ago(dt)

        attrs["status"] = "active" if is_active else "inactive"
        attrs["is_external"] = meta.get("is_external", False)
        attrs["source"] = "salesforce"
        attrs["sso_enforced"] = None
        attrs["directory_managed"] = None
        attrs["terminated_user"] = not is_active

    elif entity_type in ("org", "group"):
        attrs["mfa_required"] = None  # Requires Shield API
        attrs["sso_enforced"] = None
        attrs["externally_exposed"] = True
        attrs["directory_managed"] = None

    return attrs


def _jira_attributes(data_json: dict, entity_type: str) -> dict:
    meta = data_json.get("metadata") or {}
    attrs: dict[str, Any] = {}

    if entity_type == "user":
        attrs["mfa_enabled"] = None  # Jira REST API doesn't expose 2FA
        is_active = data_json.get("is_active", meta.get("active", True))
        attrs["is_active"] = is_active
        groups = meta.get("groups") or []
        attrs["roles"] = groups
        attrs["is_privileged"] = _is_privileged_role(groups)
        attrs["last_login_at"] = None  # Not available via Jira REST
        attrs["last_login_days_ago"] = None
        attrs["status"] = "active" if is_active else "inactive"
        attrs["is_external"] = meta.get("is_external", False)
        attrs["source"] = "jira"
        attrs["sso_enforced"] = None
        attrs["directory_managed"] = None
        attrs["terminated_user"] = not is_active

    elif entity_type in ("org", "group"):
        attrs["mfa_required"] = None
        attrs["sso_enforced"] = None
        attrs["externally_exposed"] = True
        attrs["directory_managed"] = None

    return attrs


_EXTRACTORS = {
    "github":     _github_attributes,
    "entraid":    _entraid_attributes,
    "salesforce": _salesforce_attributes,
    "jira":       _jira_attributes,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_canonical_attributes(
    data_json: dict,
    entity_type: str,
    platform: str,
) -> dict:
    """
    Merge a canonical `attributes` dict into `data_json` and return it.

    Modifies and returns the same dict (avoids a copy for performance).
    The existing `metadata` key is untouched.
    """
    extractor = _EXTRACTORS.get(platform)
    if extractor is None:
        return data_json

    canonical = extractor(data_json, entity_type)
    data_json["attributes"] = canonical
    return data_json
