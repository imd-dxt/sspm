"""
Unit tests for the GitHub connector.

All external HTTP calls are intercepted with unittest.mock.
No real GitHub App or network access required.
"""
import time
import pytest
from unittest.mock import patch, MagicMock

from connectors.github_connector import GitHubConnector
from connectors.base_connector import AuthError


# ── Fixtures ──────────────────────────────────────────────────────────────────

CREDENTIALS = {
    "app_id": "123456",
    "private_key": "",        # not needed for unit tests — token is pre-seeded
    "installation_id": "789",
}
CONFIG = {"org": "test-org"}

MOCK_USER = {"login": "alice", "id": 1, "name": "Alice Smith", "email": "alice@example.com",
             "type": "User", "site_admin": False, "public_repos": 5, "created_at": "2020-01-01T00:00:00Z"}
MOCK_MEMBER = {"login": "alice", "id": 1, "type": "User"}
MOCK_TEAM = {"id": 10, "name": "Backend", "slug": "backend", "description": "Backend team",
             "privacy": "closed", "permission": "push"}
MOCK_REPO = {"id": 100, "name": "api-service", "full_name": "test-org/api-service",
             "private": True, "visibility": "private", "default_branch": "main",
             "archived": False, "fork": False, "language": "Python",
             "owner": {"login": "test-org"}}
MOCK_COLLAB = {"login": "alice", "id": 1, "permissions": {"admin": False, "push": True, "pull": True}}
MOCK_PROTECTION = {
    "allow_force_pushes": {"enabled": False},
    "allow_deletions": {"enabled": False},
    "required_pull_request_reviews": {"required_approving_review_count": 1},
    "required_status_checks": {"strict": True, "contexts": []},
    "enforce_admins": {"enabled": True},
}
MOCK_MEMBERSHIP = {"role": "member", "state": "active"}


def _make_connector_with_token() -> GitHubConnector:
    """Create a connector and pre-seed a valid cached installation token."""
    with patch("utils.http_client.RateLimitedSession"):
        connector = GitHubConnector(credentials=CREDENTIALS, config=CONFIG)
    # Bypass _get_installation_token for all unit tests
    connector._cached_token = "fake_installation_token"
    connector._token_expires_at = time.time() + 3600
    return connector


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGitHubConnectorNormalize:
    """Test normalize_data without any HTTP calls."""

    def setup_method(self):
        self.connector = _make_connector_with_token()

    def test_normalize_user(self):
        raw = {**MOCK_USER, "github_role": "member"}
        result = self.connector.normalize_data(raw, "user")
        assert result["entity_type"] == "user"
        assert result["platform"] == "github"
        assert result["username"] == "alice"
        assert result["email"] == "alice@example.com"
        assert result["metadata"]["github_role"] == "member"

    def test_normalize_group(self):
        raw = {**MOCK_TEAM, "members": ["alice", "bob"]}
        result = self.connector.normalize_data(raw, "group")
        assert result["entity_type"] == "group"
        assert result["name"] == "Backend"
        assert result["member_count"] == 2
        assert result["metadata"]["slug"] == "backend"

    def test_normalize_resource_with_protection(self):
        raw = {**MOCK_REPO, "branch_protected": True, "allow_force_pushes": False,
               "required_pr_reviews": True, "required_status_checks": True, "enforce_admins": True}
        result = self.connector.normalize_data(raw, "resource")
        assert result["entity_type"] == "resource"
        assert result["resource_subtype"] == "repository"
        assert result["is_public"] is False
        assert result["metadata"]["branch_protected"] is True
        assert result["metadata"]["required_pr_reviews"] is True

    def test_normalize_resource_unprotected_public(self):
        raw = {**MOCK_REPO, "private": False, "visibility": "public",
               "branch_protected": False, "allow_force_pushes": True}
        result = self.connector.normalize_data(raw, "resource")
        assert result["is_public"] is True
        assert result["metadata"]["branch_protected"] is False
        assert result["metadata"]["allow_force_pushes"] is True

    def test_normalize_permission(self):
        raw = {"grantee_login": "alice", "grantee_id": "1", "repo_name": "api-service",
               "repo_id": "100", "role": "write", "permissions": {"push": True}}
        result = self.connector.normalize_data(raw, "permission")
        assert result["entity_type"] == "permission"
        assert result["role"] == "write"
        assert result["grantee_id"] == "1"
        assert result["grantee_login"] == "alice"

    def test_normalize_unknown_type_raises(self):
        with pytest.raises(Exception):
            self.connector.normalize_data({}, "unknown")


class TestGitHubConnectorAuth:

    def setup_method(self):
        self.connector = _make_connector_with_token()

    def test_authenticate_success(self):
        self.connector._http = MagicMock()
        self.connector._http.get.return_value = {"login": "test-org", "name": "Test Org"}
        assert self.connector.authenticate() is True

    def test_authenticate_401_raises_auth_error(self):
        import requests
        self.connector._http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        http_err = requests.HTTPError(response=mock_resp)
        self.connector._http.get.side_effect = http_err
        with pytest.raises(AuthError):
            self.connector.authenticate()

    def test_test_connection_ok(self):
        self.connector._http = MagicMock()
        self.connector._http.get.return_value = {"login": "test-org", "name": "Test Org"}

        mock_app_resp = MagicMock()
        mock_app_resp.ok = True
        mock_app_resp.json.return_value = {"name": "My SSPM App", "id": 123456}

        with patch("connectors.github_connector._make_app_jwt", return_value="fake_jwt"):
            with patch("connectors.github_connector.requests.get", return_value=mock_app_resp):
                result = self.connector.test_connection()

        assert result["ok"] is True
        assert result["identity"] == "My SSPM App"
        assert result["org"] == "test-org"


class TestGitHubConnectorFetch:

    def setup_method(self):
        self.connector = _make_connector_with_token()
        self.connector._http = MagicMock()

    def test_fetch_users(self):
        self.connector._http.get.side_effect = [
            [MOCK_MEMBER],   # paginate members (1 item < 100 → stops)
            MOCK_USER,       # /users/alice profile
            MOCK_MEMBERSHIP, # /orgs/.../memberships/alice
        ]
        users = self.connector.fetch_users()
        assert len(users) == 1
        assert users[0]["username"] == "alice"

    def test_fetch_groups(self):
        self.connector._http.get.side_effect = [
            [MOCK_TEAM],   # paginate teams page 1
            [],            # stop
            [MOCK_MEMBER], # paginate team members page 1
            [],            # stop
        ]
        groups = self.connector.fetch_groups()
        assert len(groups) == 1
        assert groups[0]["name"] == "Backend"

    def test_fetch_resources_with_protection(self):
        self.connector._http.get.side_effect = [
            [MOCK_REPO],     # repos page 1
            MOCK_PROTECTION, # branch protection for api-service/main
        ]
        with patch.object(self.connector, '_repo_security_features', return_value={}):
            resources = self.connector.fetch_resources()
        assert len(resources) == 1
        assert resources[0]["name"] == "api-service"
        assert resources[0]["metadata"]["branch_protected"] is True

    def test_fetch_resources_no_protection(self):
        import requests
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        http_404 = requests.HTTPError(response=mock_resp)

        self.connector._http.get.side_effect = [
            [MOCK_REPO], # repos page 1
            http_404,    # branch protection → 404 → unprotected defaults
        ]
        with patch.object(self.connector, '_repo_security_features', return_value={}):
            resources = self.connector.fetch_resources()
        assert resources[0]["metadata"]["branch_protected"] is False
        assert resources[0]["metadata"]["allow_force_pushes"] is True
