"""
GitHub connector for SSPM.

Fetches:
  - Organization metadata & security settings
  - Members (with 2FA status where accessible)
  - Teams and team memberships
  - Repositories (visibility, branch protection)
  - Repository collaborators and their permissions

Authentication:
  GitHub App (recommended).
  credentials dict must contain:
    - app_id          : GitHub App numeric ID (string)
    - private_key     : RSA private key in PEM format
    - installation_id : Installation ID for the target org
  config dict must contain:
    - org             : GitHub organization login (e.g. "my-org")
  Optionally:
    - base_url        : For GitHub Enterprise (default: https://api.github.com)

  Token generation:
    1. Sign a short-lived JWT (RS256) using the app_id + private_key
    2. Exchange the JWT for an installation access token via
       POST /app/installations/{installation_id}/access_tokens
    3. Use the installation token as a Bearer token for all API calls
    4. Tokens last 1 hour; refreshed automatically with a 5-min buffer

Rate limits:
  Authenticated: 5 000 req/hr  → ~1.38 req/s  (default)
"""
import base64
import json
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
    RateLimitError,
    SyncProgress,
)
from core.normalization import apply_canonical_attributes
from utils.http_client import RateLimitedSession

log = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


# ── JWT helper ────────────────────────────────────────────────────────────────

def _make_app_jwt(app_id: str, private_key_pem: str) -> str:
    """
    Generate a signed RS256 JWT for GitHub App authentication.
    Uses the `cryptography` package (already in requirements).
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

    now = int(time.time())
    header_b64 = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode()
    ).rstrip(b"=")
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(
            {"iat": now - 60, "exp": now + 600, "iss": str(app_id)},
            separators=(",", ":"),
        ).encode()
    ).rstrip(b"=")

    signing_input = header_b64 + b"." + payload_b64

    pem = private_key_pem if isinstance(private_key_pem, bytes) else private_key_pem.encode()
    key = serialization.load_pem_private_key(pem, password=None)
    signature = key.sign(signing_input, asym_padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")

    return f"{signing_input.decode()}.{sig_b64.decode()}"


class GitHubConnector(BaseConnector):
    """GitHub organisation connector — authenticates via GitHub App."""

    platform_name = "github"

    def __init__(self, credentials: dict[str, str], config: dict[str, Any] | None = None):
        super().__init__(credentials, config)

        self._app_id = str(credentials.get("app_id", "")).strip()
        self._private_key = credentials.get("private_key", "").strip()
        self._installation_id = str(credentials.get("installation_id", "")).strip()

        # org can come from config (preferred) or credentials (legacy)
        cfg = config or {}
        self._org: str = (cfg.get("org") or credentials.get("org", "")).strip()

        base_url: str = (cfg.get("base_url") or credentials.get("base_url") or _GITHUB_API).rstrip("/")

        self._http = RateLimitedSession(
            rate_limit_rps=1.38,  # 5000/hr
            max_retries=3,
            timeout=30,
            base_url=base_url,
        )
        # Set static headers — Authorization is filled in by _ensure_token()
        self._http.update_headers({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

        self._cached_token: str = ""
        self._token_expires_at: float = 0.0

    # ── Token management ──────────────────────────────────────────────────────

    def _get_installation_token(self) -> str:
        """
        Exchange the GitHub App JWT for an installation access token.
        Raises AuthError on any credential failure.
        """
        if not self._app_id or not self._private_key or not self._installation_id:
            raise AuthError(
                "GitHub App credentials incomplete. "
                "Provide app_id, private_key, and installation_id."
            )

        try:
            jwt_token = _make_app_jwt(self._app_id, self._private_key)
        except Exception as exc:
            raise AuthError(f"Failed to generate GitHub App JWT: {exc}") from exc

        try:
            resp = requests.post(
                f"{_GITHUB_API}/app/installations/{self._installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status in (401, 403):
                raise AuthError(
                    "GitHub App token exchange failed (401/403). "
                    "Check App ID, private key, and installation ID."
                ) from exc
            if status == 404:
                raise AuthError(
                    f"Installation ID {self._installation_id!r} not found. "
                    "Check the installation ID in GitHub App settings."
                ) from exc
            raise NetworkError(str(exc)) from exc

        data = resp.json()
        token = data.get("token", "")
        if not token:
            raise AuthError("GitHub API returned empty installation token.")

        # Cache the token expiry
        expires_at_str = data.get("expires_at")
        if expires_at_str:
            try:
                exp = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                self._token_expires_at = exp.timestamp()
            except Exception:
                self._token_expires_at = time.time() + 3600
        else:
            self._token_expires_at = time.time() + 3600

        self._cached_token = token
        return token

    def _ensure_token(self) -> None:
        """Refresh the installation token if expired (5-min buffer) and update HTTP headers."""
        if self._cached_token and time.time() < self._token_expires_at - 300:
            return
        token = self._get_installation_token()
        self._http.update_headers({"Authorization": f"Bearer {token}"})

    # ── Auth / connection ─────────────────────────────────────────────────────

    def authenticate(self) -> bool:
        self._ensure_token()
        try:
            if self._org:
                self._http.get(f"/orgs/{self._org}")
            else:
                # List first repo accessible by this installation as a health-check
                self._http.get("/installation/repositories", params={"per_page": 1})
            self._log.info(
                "github_app_authenticated",
                extra={"app_id": self._app_id, "org": self._org},
            )
            return True
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 403):
                raise AuthError(
                    "GitHub App access denied. Ensure the app is installed on "
                    f"org '{self._org}' with the required permissions."
                ) from exc
            raise NetworkError(str(exc)) from exc

    def test_connection(self) -> dict[str, Any]:
        self._ensure_token()
        try:
            org_data = self._http.get(f"/orgs/{self._org}") if self._org else {}

            # Fetch app metadata via JWT (separate request — installation token can't call /app)
            try:
                jwt_token = _make_app_jwt(self._app_id, self._private_key)
                app_resp = requests.get(
                    f"{_GITHUB_API}/app",
                    headers={
                        "Authorization": f"Bearer {jwt_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=30,
                )
                app_data = app_resp.json() if app_resp.ok else {}
            except Exception:
                app_data = {}

            return {
                "ok": True,
                "platform": "github",
                "identity": app_data.get("name") or f"App {self._app_id}",
                "app_id": self._app_id,
                "installation_id": self._installation_id,
                "org": org_data.get("login") or self._org,
                "org_name": org_data.get("name"),
            }
        except Exception as exc:
            return {"ok": False, "platform": "github", "error": str(exc)}

    # ── Fetchers ──────────────────────────────────────────────────────────────

    def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
        params = dict(params or {})
        params["per_page"] = 100
        results: list[dict] = []
        page = 1
        while True:
            params["page"] = page
            data = self._http.get(path, params=params)
            if not isinstance(data, list) or not data:
                break
            results.extend(data)
            if len(data) < 100:
                break
            page += 1
        return results

    def _branch_protection(self, repo: str, branch: str) -> dict[str, Any]:
        """Return full branch protection posture.
        404 → no rule (fully unprotected).
        403 → insufficient permissions; treat as unknown/unprotected and warn.
        """
        _unprotected = {
            "branch_protected": False,
            "allow_force_pushes": True,
            "allow_deletions": True,
            "required_pr_reviews": False,
            "required_approving_review_count": 0,
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
            "require_status_checks": False,
            "required_status_check_contexts": [],
            "require_signed_commits": False,
            "enforce_admins": False,
        }
        try:
            data = self._http.get(f"/repos/{self._org}/{repo}/branches/{branch}/protection")
            pr_reviews = data.get("required_pull_request_reviews") or {}
            status_checks = data.get("required_status_checks") or {}
            return {
                "branch_protected": True,
                "allow_force_pushes": data.get("allow_force_pushes", {}).get("enabled", False),
                "allow_deletions": data.get("allow_deletions", {}).get("enabled", False),
                "required_pr_reviews": bool(pr_reviews),
                "required_approving_review_count": pr_reviews.get("required_approving_review_count", 0),
                "dismiss_stale_reviews": pr_reviews.get("dismiss_stale_reviews", False),
                "require_code_owner_reviews": pr_reviews.get("require_code_owner_reviews", False),
                "require_status_checks": bool(status_checks),
                "required_status_check_contexts": status_checks.get("contexts", []),
                "require_signed_commits": data.get("required_signatures", {}).get("enabled", False),
                "enforce_admins": data.get("enforce_admins", {}).get("enabled", False),
            }
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 404:
                return _unprotected
            if status == 403:
                self._log.warning(
                    "github_branch_protection_forbidden",
                    extra={
                        "repo": repo,
                        "hint": "Grant 'Administration: read' (Repository permission) to the GitHub App",
                    },
                )
                return _unprotected
            raise

    def _file_exists(self, repo: str, *candidate_paths: str) -> bool:
        """Return True if any of the candidate paths exist in the repo."""
        for path in candidate_paths:
            try:
                self._http.get(f"/repos/{self._org}/{repo}/contents/{path}")
                return True
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    continue
                break
        return False

    def _repo_security_features(self, repo: str) -> dict[str, Any]:
        """Fetch security feature flags and file presence for a repo."""
        result: dict[str, Any] = {
            "secret_scanning_enabled": False,
            "code_scanning_enabled": False,
            "dependabot_enabled": False,
            "has_security_policy": False,
            "has_codeowners": False,
        }
        try:
            data = self._http.get(f"/repos/{self._org}/{repo}")
            sa = data.get("security_and_analysis") or {}
            result["secret_scanning_enabled"] = sa.get("secret_scanning", {}).get("status") == "enabled"
            result["code_scanning_enabled"] = sa.get("code_scanning_default_setup", {}).get("status") == "configured"
            result["dependabot_enabled"] = sa.get("dependabot_security_updates", {}).get("status") == "enabled"
        except Exception:
            pass

        result["has_security_policy"] = self._file_exists(repo, "SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md")
        result["has_codeowners"] = self._file_exists(repo, "CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
        return result

    def fetch_org(self) -> list[dict[str, Any]]:
        """Fetch org-level settings and security configuration."""
        data = self._http.get(f"/orgs/{self._org}")
        return [self.normalize_data(data, entity_type="org")]

    def fetch_users(self) -> list[dict[str, Any]]:
        """Fetch org members and normalize each to NormalizedUser schema."""
        raw_members = self._paginate(f"/orgs/{self._org}/members")
        users = []
        for m in raw_members:
            try:
                profile = self._http.get(f"/users/{m['login']}")
            except Exception:
                profile = m

            try:
                member_detail = self._http.get(f"/orgs/{self._org}/memberships/{m['login']}")
                role = member_detail.get("role", "member")
            except Exception:
                role = "member"

            users.append(self.normalize_data(
                {**m, **profile, "github_role": role},
                entity_type="user",
            ))
        return users

    def fetch_groups(self) -> list[dict[str, Any]]:
        """Fetch teams and normalize each to NormalizedGroup schema."""
        try:
            raw_teams = self._paginate(f"/orgs/{self._org}/teams")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                self._log.warning(
                    "github_teams_forbidden",
                    extra={"hint": "Grant 'Members: read' (Organization permission) to the GitHub App"},
                )
                return []
            raise
        groups = []
        for t in raw_teams:
            try:
                members = self._paginate(f"/orgs/{self._org}/teams/{t['slug']}/members")
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 403:
                    members = []
                else:
                    raise
            groups.append(self.normalize_data(
                {**t, "members": [m["login"] for m in members]},
                entity_type="group",
            ))
        return groups

    @staticmethod
    def _flags_from_default(perm: str) -> dict[str, bool]:
        return {
            "admin":    perm == "admin",
            "maintain": False,
            "push":     perm in ("admin", "write"),
            "triage":   perm in ("admin", "write"),
            "pull":     perm in ("admin", "write", "read"),
        }

    @staticmethod
    def _role_from_flags(flags: dict) -> str:
        if flags.get("admin"):    return "admin"
        if flags.get("maintain"): return "maintain"
        if flags.get("push"):     return "write"
        if flags.get("triage"):   return "triage"
        if flags.get("pull"):     return "read"
        return "none"

    def fetch_permissions(self) -> list[dict[str, Any]]:
        """Build a complete (user × repo) permission matrix."""
        try:
            org_data = self._http.get(f"/orgs/{self._org}")
            default_perm = org_data.get("default_repository_permission", "read") or "read"
        except Exception:
            default_perm = "read"

        all_members: dict[str, str] = {
            m["login"]: str(m["id"])
            for m in self._paginate(f"/orgs/{self._org}/members")
        }

        permissions = []
        repos = self._paginate(f"/orgs/{self._org}/repos")

        for repo in repos:
            try:
                collabs = self._paginate(
                    f"/repos/{self._org}/{repo['name']}/collaborators",
                    params={"affiliation": "all"},
                )
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 403:
                    self._log.warning(
                        "github_collaborators_forbidden",
                        extra={
                            "repo": repo["name"],
                            "hint": "Grant 'Members: read' (Organization permission) to the GitHub App",
                        },
                    )
                    collabs = []
                else:
                    raise

            explicit: dict[str, dict] = {}
            for c in collabs:
                flags = {
                    "admin":    c.get("permissions", {}).get("admin", False),
                    "maintain": c.get("permissions", {}).get("maintain", False),
                    "push":     c.get("permissions", {}).get("push", False),
                    "triage":   c.get("permissions", {}).get("triage", False),
                    "pull":     c.get("permissions", {}).get("pull", False),
                }
                explicit[c["login"]] = {"id": str(c["id"]), "flags": flags}

            for login, user_numeric_id in all_members.items():
                if login in explicit:
                    entry = explicit[login]
                    flags  = entry["flags"]
                    source = "explicit"
                    uid    = entry["id"]
                else:
                    flags  = self._flags_from_default(default_perm)
                    source = "org_default"
                    uid    = user_numeric_id

                role = self._role_from_flags(flags)
                permissions.append(self.normalize_data(
                    {
                        "grantee_login":    login,
                        "grantee_id":       uid,
                        "repo_name":        repo["name"],
                        "repo_id":          str(repo["id"]),
                        "role":             role,
                        "permissions":      flags,
                        "source":           source,
                        "org_default_perm": default_perm,
                    },
                    entity_type="permission",
                ))

        return permissions

    def fetch_resources(self) -> list[dict[str, Any]]:
        """Fetch repositories with full CIS-required metadata."""
        raw_repos = self._paginate(f"/orgs/{self._org}/repos")
        resources = []
        for r in raw_repos:
            name = r["name"]
            default_branch = r.get("default_branch", "main")
            protection = self._branch_protection(name, default_branch)
            security = self._repo_security_features(name)

            last_push = r.get("pushed_at")
            days_inactive: int | None = None
            if last_push:
                try:
                    pushed = datetime.fromisoformat(last_push.replace("Z", "+00:00"))
                    days_inactive = (datetime.now(timezone.utc) - pushed).days
                except Exception:
                    pass

            resources.append(self.normalize_data(
                {**r, **protection, **security, "last_pushed_days_ago": days_inactive},
                entity_type="resource",
            ))
        return resources

    # ── Normalization ─────────────────────────────────────────────────────────

    def normalize_data(self, raw: dict[str, Any], entity_type: str) -> dict[str, Any]:
        result = self._normalize_raw(raw, entity_type)
        return apply_canonical_attributes(result, entity_type, "github")

    def _normalize_raw(self, raw: dict[str, Any], entity_type: str) -> dict[str, Any]:  # noqa: C901
        if entity_type == "org":
            return {
                "entity_type": "org",
                "platform": "github",
                "platform_id": raw.get("login", ""),
                "name": raw.get("name") or raw.get("login", ""),
                "metadata": {
                    "two_factor_required": raw.get("two_factor_requirement_enabled"),
                    "default_repo_permission": raw.get("default_repository_permission"),
                    "members_can_create_repos": raw.get("members_can_create_repositories"),
                    "members_can_create_public_repos": raw.get("members_can_create_public_repositories"),
                    "members_can_create_private_repos": raw.get("members_can_create_private_repositories"),
                    "public_repos": raw.get("public_repos"),
                    "total_private_repos": raw.get("total_private_repos"),
                    "plan": raw.get("plan", {}).get("name") if raw.get("plan") else None,
                },
            }

        if entity_type == "user":
            return {
                "entity_type": "user",
                "platform": "github",
                "platform_id": str(raw.get("id", raw.get("login", ""))),
                "email": raw.get("email"),
                "username": raw.get("login"),
                "display_name": raw.get("name") or raw.get("login"),
                "is_active": True,
                "is_external": raw.get("type", "User") != "User",
                "created_at": raw.get("created_at"),
                "metadata": {
                    "two_factor_enabled": raw.get("two_factor_authentication"),
                    "github_role": raw.get("github_role", "member"),
                    "site_admin": raw.get("site_admin", False),
                    "public_repos": raw.get("public_repos"),
                    "avatar_url": raw.get("avatar_url"),
                },
            }

        if entity_type == "group":
            return {
                "entity_type": "group",
                "platform": "github",
                "platform_id": str(raw.get("id", "")),
                "name": raw.get("name", ""),
                "description": raw.get("description"),
                "member_count": len(raw.get("members", [])),
                "metadata": {
                    "slug": raw.get("slug"),
                    "privacy": raw.get("privacy"),
                    "permission": raw.get("permission"),
                    "members": raw.get("members", []),
                },
            }

        if entity_type == "resource":
            return {
                "entity_type": "resource",
                "platform": "github",
                "platform_id": str(raw.get("id", "")),
                "name": raw.get("name", ""),
                "resource_subtype": "repository",
                "is_public": not raw.get("private", True),
                "owner_id": raw.get("owner", {}).get("login") if raw.get("owner") else None,
                "metadata": {
                    "full_name": raw.get("full_name"),
                    "visibility": raw.get("visibility"),
                    "default_branch": raw.get("default_branch"),
                    "archived": raw.get("archived", False),
                    "is_fork": raw.get("fork", False),
                    "language": raw.get("language"),
                    "last_pushed_days_ago": raw.get("last_pushed_days_ago"),
                    "branch_protected": raw.get("branch_protected", False),
                    "allow_force_pushes": raw.get("allow_force_pushes", True),
                    "allow_deletions": raw.get("allow_deletions", True),
                    "enforce_admins": raw.get("enforce_admins", False),
                    "required_pr_reviews": raw.get("required_pr_reviews", False),
                    "required_approving_review_count": raw.get("required_approving_review_count", 0),
                    "dismiss_stale_reviews": raw.get("dismiss_stale_reviews", False),
                    "require_code_owner_reviews": raw.get("require_code_owner_reviews", False),
                    "require_status_checks": raw.get("require_status_checks", False),
                    "required_status_check_contexts": raw.get("required_status_check_contexts", []),
                    "require_signed_commits": raw.get("require_signed_commits", False),
                    "secret_scanning_enabled": raw.get("secret_scanning_enabled", False),
                    "code_scanning_enabled": raw.get("code_scanning_enabled", False),
                    "dependabot_enabled": raw.get("dependabot_enabled", False),
                    "has_security_policy": raw.get("has_security_policy", False),
                    "has_codeowners": raw.get("has_codeowners", False),
                },
            }

        if entity_type == "permission":
            grantee_login = raw.get("grantee_login", "")
            grantee_numeric_id = raw.get("grantee_id", grantee_login)
            repo_name = raw.get("repo_name", "")
            repo_numeric_id = raw.get("repo_id", repo_name)
            return {
                "entity_type": "permission",
                "platform": "github",
                "platform_id": f"{grantee_login}:{repo_name}",
                "grantee_id": grantee_numeric_id,
                "grantee_login": grantee_login,
                "grantee_type": "user",
                "resource_id": repo_numeric_id,
                "resource_name": repo_name,
                "role": raw.get("role", "none"),
                "perm_admin":    raw.get("permissions", {}).get("admin", False),
                "perm_maintain": raw.get("permissions", {}).get("maintain", False),
                "perm_push":     raw.get("permissions", {}).get("push", False),
                "perm_triage":   raw.get("permissions", {}).get("triage", False),
                "perm_pull":     raw.get("permissions", {}).get("pull", False),
                "source": raw.get("source", "explicit"),
                "org_default_perm": raw.get("org_default_perm"),
            }

        raise ParseError(f"Unknown entity_type: {entity_type!r}")

    # ── Full sync ─────────────────────────────────────────────────────────────

    def sync(self) -> SyncProgress:
        progress = self._start_progress()

        try:
            self.authenticate()
        except AuthError as exc:
            progress.record_error("authenticate", str(exc))
            progress.finish()
            return progress

        entity_fetchers = [
            ("org", self.fetch_org),
            ("users", self.fetch_users),
            ("groups", self.fetch_groups),
            ("resources", self.fetch_resources),
            ("permissions", self.fetch_permissions),
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

        progress.entities = all_entities  # type: ignore[attr-defined]
        self._finish_progress()
        return progress

    def fetch_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Fetch recent organization audit log entries.
        Requires the GitHub App to have the `organization_administration: read` permission.
        """
        if not self._org:
            return []
        try:
            data = self._http.get(f"/orgs/{self._org}/audit-log", params={"per_page": limit})
            entries = data if isinstance(data, list) else []
        except Exception as exc:
            log.warning("github_audit_log_error: %s", exc)
            return []

        result = []
        for e in entries:
            result.append({
                "actor": e.get("actor"),
                "action": e.get("action", ""),
                "resource": e.get("repo") or e.get("org") or e.get("user"),
                "timestamp": _parse_gh_ts(e.get("created_at") or e.get("@timestamp")),
                "raw": e,
            })
        return result


def _parse_gh_ts(value: Any) -> Any:
    """Convert GitHub audit log timestamp to ISO string."""
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return value
