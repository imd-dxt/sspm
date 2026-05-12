"""Unit tests for the detection rules engine."""
import pytest
from core.rules_engine import RulesEngine, RuleResult


def _repo(name: str, **overrides) -> dict:
    base = {
        "entity_type": "resource",
        "platform": "github",
        "platform_id": "100",
        "name": name,
        "resource_subtype": "repository",
        "is_public": False,
        "metadata": {
            "branch_protected": True,
            "allow_force_pushes": False,
            "allow_deletions": False,
            "required_pr_reviews": True,
            "required_status_checks": True,
            "enforce_admins": True,
        },
    }
    # Allow overriding nested metadata
    if "metadata" in overrides:
        base["metadata"].update(overrides.pop("metadata"))
    base.update(overrides)
    return base


def _user(username: str, two_fa: bool | None = True) -> dict:
    return {
        "entity_type": "user",
        "platform": "github",
        "platform_id": "1",
        "username": username,
        "metadata": {"two_factor_enabled": two_fa, "github_role": "member"},
    }


class TestRulesEngine:

    def setup_method(self):
        self.engine = RulesEngine()

    def _find(self, findings: list[RuleResult], rule_id: str) -> list[RuleResult]:
        return [f for f in findings if f.rule_id == rule_id]

    # ── GH-001 public repo ────────────────────────────────────────────────────

    def test_gh001_public_repo_triggers(self):
        entities = [_repo("public-repo", is_public=True)]
        findings = self.engine.run(entities)
        assert self._find(findings, "GH-001")

    def test_gh001_private_repo_no_trigger(self):
        entities = [_repo("private-repo", is_public=False)]
        findings = self.engine.run(entities)
        assert not self._find(findings, "GH-001")

    # ── GH-002 missing branch protection ─────────────────────────────────────

    def test_gh002_no_protection_triggers(self):
        entities = [_repo("unprotected", metadata={"branch_protected": False})]
        findings = self.engine.run(entities)
        assert self._find(findings, "GH-002")

    def test_gh002_protected_no_trigger(self):
        entities = [_repo("protected")]
        findings = self.engine.run(entities)
        assert not self._find(findings, "GH-002")

    # ── GH-003 force pushes ───────────────────────────────────────────────────

    def test_gh003_force_pushes_triggers(self):
        entities = [_repo("fp-repo", metadata={"branch_protected": True, "allow_force_pushes": True})]
        findings = self.engine.run(entities)
        assert self._find(findings, "GH-003")

    def test_gh003_no_force_pushes_no_trigger(self):
        entities = [_repo("ok-repo")]
        findings = self.engine.run(entities)
        assert not self._find(findings, "GH-003")

    # ── GH-004 no PR reviews ─────────────────────────────────────────────────

    def test_gh004_no_reviews_triggers(self):
        entities = [_repo("no-review", metadata={"branch_protected": True, "required_pr_reviews": False})]
        findings = self.engine.run(entities)
        assert self._find(findings, "GH-004")

    # ── GH-005 no 2FA ─────────────────────────────────────────────────────────

    def test_gh005_no_2fa_triggers(self):
        entities = [_user("bob", two_fa=False)]
        findings = self.engine.run(entities)
        assert self._find(findings, "GH-005")

    def test_gh005_2fa_enabled_no_trigger(self):
        entities = [_user("alice", two_fa=True)]
        findings = self.engine.run(entities)
        assert not self._find(findings, "GH-005")

    def test_gh005_2fa_unknown_no_trigger(self):
        """None means we couldn't determine 2FA status – do not false-positive."""
        entities = [_user("unknown", two_fa=None)]
        findings = self.engine.run(entities)
        assert not self._find(findings, "GH-005")

    # ── Severity fields ───────────────────────────────────────────────────────

    def test_finding_has_required_fields(self):
        entities = [_repo("bad-repo", is_public=True, metadata={"branch_protected": False})]
        findings = self.engine.run(entities)
        for f in findings:
            assert f.rule_id
            assert f.severity in ("critical", "high", "medium", "low", "info")
            assert f.title
            assert f.description
            assert f.remediation
