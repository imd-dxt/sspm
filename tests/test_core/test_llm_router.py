"""Tests for core/llm_router.py — privacy and routing guarantees."""
import pytest
from core.llm_router import LLMRouter, SENSITIVE_FIELDS, TASK_ROUTING


@pytest.fixture
def router():
    return LLMRouter()


class TestSanitise:
    def test_removes_all_sensitive_fields(self, router):
        data = {
            "username": "john.doe",
            "email": "john@acme.com",
            "severity": "critical",
            "score": 67,
            "display_name": "John Doe",
            "tenant_id": "abc-123",
            "rule_id": "CIS-1.1.1",
        }
        sanitised, token_map = router.sanitise(data)
        for field in SENSITIVE_FIELDS:
            if field in sanitised:
                assert sanitised[field].startswith("TOKEN_"), (
                    f"Field '{field}' was not tokenised: {sanitised[field]!r}"
                )
        assert sanitised["severity"] == "critical"
        assert sanitised["score"] == 67
        assert sanitised["rule_id"] == "CIS-1.1.1"

    def test_detokenise_restores_values(self, router):
        data = {"email": "alice@example.com", "username": "alice"}
        sanitised, token_map = router.sanitise(data)
        restored_email = router.de_tokenise(sanitised["email"], token_map)
        assert restored_email == "alice@example.com"

    def test_email_in_string_tokenised(self, router):
        data = {"description": "Contact admin@company.com for access"}
        sanitised, token_map = router.sanitise(data)
        assert "admin@company.com" not in sanitised["description"]

    def test_nested_sensitive_fields(self, router):
        data = {"finding": {"username": "bob", "severity": "high"}}
        sanitised, token_map = router.sanitise(data)
        assert sanitised["finding"]["username"].startswith("TOKEN_")
        assert sanitised["finding"]["severity"] == "high"

    def test_empty_values_not_tokenised(self, router):
        data = {"username": "", "severity": "low"}
        sanitised, token_map = router.sanitise(data)
        assert sanitised["username"] == ""
        assert len(token_map) == 0


class TestRouting:
    def test_deepseek_tasks_are_routed_correctly(self):
        deepseek_tasks = [
            "executive_summary", "impact_analysis",
            "compliance_insights", "exploitation_scenario", "trend_narrative",
        ]
        for task in deepseek_tasks:
            assert TASK_ROUTING.get(task) == "deepseek", (
                f"Task '{task}' should route to deepseek"
            )

    def test_ollama_tasks_are_routed_correctly(self):
        ollama_tasks = ["remediation_steps", "finding_explanation", "qa_answer"]
        for task in ollama_tasks:
            assert TASK_ROUTING.get(task) == "ollama", (
                f"Task '{task}' should route to ollama"
            )

    def test_generate_returns_fallback_when_llms_unavailable(self, router):
        # With no real Ollama/DeepSeek connections, generate() must never raise
        result = router.generate("executive_summary", {"score": 72},
                                  fallback_text="FALLBACK")
        assert isinstance(result, str)

    def test_deepseek_never_called_with_raw_sensitive_data(self, monkeypatch, router):
        """Verify that call_deepseek never receives un-tokenised sensitive values."""
        captured_prompts: list[str] = []

        def fake_deepseek(prompt, system=None, timeout=None):
            captured_prompts.append(prompt)
            return "AI response"

        monkeypatch.setattr(router, "call_deepseek", fake_deepseek)

        sensitive_data = {
            "username": "real_user",
            "email": "real@company.com",
            "severity": "critical",
            "score": 45,
        }
        router.generate("executive_summary", sensitive_data)

        for prompt in captured_prompts:
            assert "real_user" not in prompt, "Raw username sent to DeepSeek"
            assert "real@company.com" not in prompt, "Raw email sent to DeepSeek"
