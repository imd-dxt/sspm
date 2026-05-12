"""
Unit tests for the GitHub connector.

All external HTTP calls are intercepted with responses/unittest.mock.
No real GitHub token or network access required.
"""
import pytest
from unittest.mock import patch, MagicMock

from connectors.github_connector import GitHubConnector
from connectors.base_connector import AuthError


# ── Fixtures ──────────────────────────────────────────────────────────────────

CREDENTIALS = {"token": "ghp_test_token"}
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


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGitHubConnectorNormalize:
    """Test normalize_data without any HTTP calls."""

    def setup_method(self):
        with patch("utils.http_client.RateLimitedSession"):
            self.connector = GitHubConnector(credentials=CREDENTIALS, config=CONFIG)

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
        # grantee_id stores the numeric GitHub user ID so it joins against
        # user.platform_id (also a numeric string); login is kept separately.
        assert result["grantee_id"] == "1"
        assert result["grantee_login"] == "alice"

    def test_normalize_unknown_type_raises(self):
        with pytest.raises(Exception):
            self.connector.normalize_data({}, "unknown")


class TestGitHubConnectorAuth:

    def setup_method(self):
        with patch("utils.http_client.RateLimitedSession"):
            self.connector = GitHubConnector(credentials=CREDENTIALS, config=CONFIG)

    def test_authenticate_success(self):
        self.connector._http = MagicMock()
        self.connector._http.get.return_value = {"login": "alice"}
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
        self.connector._http.get.side_effect = [
            {"login": "alice"},           # /user
            {"login": "test-org", "name": "Test Org"},  # /orgs/test-org
        ]
        result = self.connector.test_connection()
        assert result["ok"] is True
        assert result["identity"] == "alice"
        assert result["org"] == "test-org"


class TestGitHubConnectorFetch:

    def setup_method(self):
        with patch("utils.http_client.RateLimitedSession"):
            self.connector = GitHubConnector(credentials=CREDENTIALS, config=CONFIG)
        self.connector._http = MagicMock()

    def test_fetch_users(self):
        # _paginate stops after the first page when len(data) < 100 — no extra call.
        self.connector._http.get.side_effect = [
            [MOCK_MEMBER],   # paginate members (1 item < 100 → stops, no page-2 call)
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
        # _paginate stops after page 1 (1 item < 100).
        # _repo_security_features makes several extra HTTP calls; patch it out
        # so this test stays focused on the branch-protection path.
        self.connector._http.get.side_effect = [
            [MOCK_REPO],     # repos page 1 (stops, no page-2 call)
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
            [MOCK_REPO], # repos page 1 (stops, no page-2 call)
            http_404,    # branch protection → 404 → unprotected defaults
        ]
        with patch.object(self.connector, '_repo_security_features', return_value={}):
            resources = self.connector.fetch_resources()
        assert resources[0]["metadata"]["branch_protected"] is False
        assert resources[0]["metadata"]["allow_force_pushes"] is True
