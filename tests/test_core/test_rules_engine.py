"""
Tests for the detection rules engine.

The current architecture splits rule evaluation into two layers:
  - core/normalized_rules_engine.py  — pure-Python condition evaluator (no DB needed)
  - core/rules_engine.py             — DB/Neo4j orchestrator (requires live session)

These tests cover the condition evaluator directly, which is where the detection
logic lives.  The orchestrator is integration-tested via the scan pipeline tests.
"""
import pytest
from unittest.mock import MagicMock

from core.normalized_rules_engine import _eval_condition, _eval_leaf, _get_field
from core.rules_engine import RulesEngine


# ── _get_field ────────────────────────────────────────────────────────────────

class TestGetField:
    def test_top_level_present(self):
        val, exists = _get_field({"foo": "bar"}, "foo")
        assert exists is True
        assert val == "bar"

    def test_top_level_missing(self):
        val, exists = _get_field({}, "foo")
        assert exists is False
        assert val is None

    def test_nested_dot_notation(self):
        val, exists = _get_field({"attributes": {"mfa_enabled": False}}, "attributes.mfa_enabled")
        assert exists is True
        assert val is False

    def test_nested_missing_parent(self):
        _, exists = _get_field({}, "attributes.mfa_enabled")
        assert exists is False

    def test_nested_parent_not_dict(self):
        _, exists = _get_field({"attributes": "string"}, "attributes.mfa_enabled")
        assert exists is False


# ── _eval_leaf — operator coverage ───────────────────────────────────────────

class TestEvalLeaf:
    def _cond(self, field, operator, value=None):
        c = {"field": field, "operator": operator}
        if value is not None:
            c["value"] = value
        return c

    def test_equals_match(self):
        assert _eval_leaf({"status": "active"}, self._cond("status", "equals", "active"))

    def test_equals_no_match(self):
        assert not _eval_leaf({"status": "inactive"}, self._cond("status", "equals", "active"))

    def test_not_equals(self):
        assert _eval_leaf({"role": "viewer"}, self._cond("role", "not_equals", "admin"))

    def test_exists_present(self):
        assert _eval_leaf({"token": "abc"}, self._cond("token", "exists"))

    def test_exists_missing(self):
        assert not _eval_leaf({}, self._cond("token", "exists"))

    def test_exists_none_value(self):
        assert not _eval_leaf({"token": None}, self._cond("token", "exists"))

    def test_not_exists(self):
        assert _eval_leaf({}, self._cond("token", "not_exists"))

    def test_is_empty_none(self):
        assert _eval_leaf({"x": None}, self._cond("x", "is_empty"))

    def test_is_empty_empty_list(self):
        assert _eval_leaf({"x": []}, self._cond("x", "is_empty"))

    def test_is_empty_nonempty_list(self):
        assert not _eval_leaf({"x": [1]}, self._cond("x", "is_empty"))

    def test_is_empty_missing_key(self):
        assert _eval_leaf({}, self._cond("missing", "is_empty"))

    def test_contains_match(self):
        assert _eval_leaf({"roles": ["admin", "viewer"]}, self._cond("roles", "contains", "admin"))

    def test_contains_no_match(self):
        assert not _eval_leaf({"roles": ["viewer"]}, self._cond("roles", "contains", "admin"))

    def test_contains_non_list(self):
        assert not _eval_leaf({"roles": "admin"}, self._cond("roles", "contains", "admin"))

    def test_older_than_days_triggers(self):
        # 2000-01-01 is definitely more than 90 days ago
        assert _eval_leaf(
            {"last_login": "2000-01-01T00:00:00Z"},
            {"field": "last_login", "operator": "older_than_days", "value": 90},
        )

    def test_older_than_days_recent_no_trigger(self):
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        assert not _eval_leaf(
            {"last_login": recent},
            {"field": "last_login", "operator": "older_than_days", "value": 90},
        )

    def test_older_than_days_missing_field(self):
        assert not _eval_leaf({}, {"field": "last_login", "operator": "older_than_days", "value": 90})

    def test_unknown_operator_returns_false(self):
        assert not _eval_leaf({"x": 1}, self._cond("x", "bogus_op", 1))


# ── _eval_condition — compound logic ─────────────────────────────────────────

class TestEvalCondition:
    def test_all_passes(self):
        cond = {"all": [
            {"field": "attributes.mfa_enabled", "operator": "equals", "value": False},
            {"field": "attributes.is_active",   "operator": "equals", "value": True},
        ]}
        data = {"attributes": {"mfa_enabled": False, "is_active": True}}
        assert _eval_condition(data, cond)

    def test_all_fails_one(self):
        cond = {"all": [
            {"field": "attributes.mfa_enabled", "operator": "equals", "value": False},
            {"field": "attributes.is_active",   "operator": "equals", "value": True},
        ]}
        data = {"attributes": {"mfa_enabled": True, "is_active": True}}
        assert not _eval_condition(data, cond)

    def test_any_one_match(self):
        cond = {"any": [
            {"field": "attributes.is_admin",    "operator": "equals", "value": True},
            {"field": "attributes.mfa_enabled", "operator": "equals", "value": False},
        ]}
        data = {"attributes": {"is_admin": False, "mfa_enabled": False}}
        assert _eval_condition(data, cond)

    def test_any_no_match(self):
        cond = {"any": [
            {"field": "attributes.is_admin",    "operator": "equals", "value": True},
            {"field": "attributes.mfa_enabled", "operator": "equals", "value": False},
        ]}
        data = {"attributes": {"is_admin": False, "mfa_enabled": True}}
        assert not _eval_condition(data, cond)

    def test_nested_all_inside_any(self):
        cond = {"any": [
            {"all": [
                {"field": "attributes.is_admin",    "operator": "equals", "value": True},
                {"field": "attributes.mfa_enabled", "operator": "equals", "value": False},
            ]},
            {"field": "attributes.is_external", "operator": "equals", "value": True},
        ]}
        # Second branch matches (external user)
        data = {"attributes": {"is_admin": False, "mfa_enabled": True, "is_external": True}}
        assert _eval_condition(data, cond)

    def test_unknown_node_returns_false(self):
        assert not _eval_condition({}, {"unknown_key": []})


# ── Realistic detection scenarios ────────────────────────────────────────────

class TestDetectionScenarios:
    """
    Simulate what the YAML rules do: define a condition dict, feed entity data,
    assert the match result.  These mirror the GH-* rule intent without
    needing the database.
    """

    # Simulates GH-001: public repository
    def test_public_repo_detected(self):
        cond = {"field": "attributes.is_public", "operator": "equals", "value": True}
        assert _eval_condition({"attributes": {"is_public": True}}, cond)
        assert not _eval_condition({"attributes": {"is_public": False}}, cond)

    # Simulates GH-002: no branch protection
    def test_no_branch_protection(self):
        cond = {"field": "attributes.branch_protected", "operator": "equals", "value": False}
        assert _eval_condition({"attributes": {"branch_protected": False}}, cond)
        assert not _eval_condition({"attributes": {"branch_protected": True}}, cond)

    # Simulates GH-003: force pushes allowed
    def test_force_pushes_allowed(self):
        cond = {"all": [
            {"field": "attributes.branch_protected",   "operator": "equals", "value": True},
            {"field": "attributes.allow_force_pushes", "operator": "equals", "value": True},
        ]}
        assert _eval_condition(
            {"attributes": {"branch_protected": True, "allow_force_pushes": True}}, cond
        )
        assert not _eval_condition(
            {"attributes": {"branch_protected": True, "allow_force_pushes": False}}, cond
        )

    # Simulates GH-005: 2FA not enabled (explicitly False — None = unknown, skip)
    def test_2fa_disabled_detected(self):
        cond = {"field": "attributes.mfa_enabled", "operator": "equals", "value": False}
        assert _eval_condition({"attributes": {"mfa_enabled": False}}, cond)
        assert not _eval_condition({"attributes": {"mfa_enabled": True}}, cond)
        # None (unknown) must NOT trigger a false positive
        assert not _eval_condition({"attributes": {"mfa_enabled": None}}, cond)


# ── RulesEngine constructor smoke test ────────────────────────────────────────

class TestRulesEngineConstruct:
    def test_instantiates_with_mocked_deps(self):
        db    = MagicMock()
        graph = MagicMock()
        engine = RulesEngine(db=db, graph=graph, connector_id="c1", connector_name="Test")
        assert engine._connector_id == "c1"
        assert engine._connector_name == "Test"

    def test_extract_identifier_named_field(self):
        row = {"repository": "my-repo", "other": "val"}
        assert RulesEngine._extract_identifier(row, "repository") == "my-repo"

    def test_extract_identifier_fallback(self):
        row = {"other": "val"}
        result = RulesEngine._extract_identifier(row, "missing_field")
        assert result == "val"

    def test_infer_resource_type_known(self):
        assert RulesEngine._infer_resource_type("repository") == "repository"
        assert RulesEngine._infer_resource_type("user") == "user"

    def test_infer_resource_type_unknown_passthrough(self):
        assert RulesEngine._infer_resource_type("custom_field") == "custom_field"
