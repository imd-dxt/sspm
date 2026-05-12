"""
LLM Judge – re-evaluates security findings using DeepSeek AI via LangChain.

For each finding the judge:
  1. Re-checks severity in the context of the tenant/environment
  2. Explains how the finding could realistically be exploited
  3. Provides enhanced, context-aware remediation steps
  4. Returns a confidence score (0-1)

Usage:
    from core.llm_judge import LLMJudge
    judge = LLMJudge()
    result = judge.analyze(finding_dict, rule_dict)
"""
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class LLMJudgeResult(BaseModel):
    """Structured output returned by the LLM judge for a single finding."""

    severity: str = Field(
        description="Reassessed severity: critical | high | medium | low | info"
    )
    severity_reasoning: str = Field(
        description="Why this severity was chosen given the specific context"
    )
    exploitability: str = Field(
        description="Step-by-step scenario of how an attacker could exploit this finding"
    )
    remediation: str = Field(
        description="Enhanced, context-specific remediation guidance"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in this assessment (0 = uncertain, 1 = very confident)"
    )


class LLMJudge:
    """
    Wraps DeepSeek AI (OpenAI-compatible API) to re-analyze security findings.

    Requires DEEPSEEK_API_KEY in environment / .env.
    """

    def __init__(self) -> None:
        from config.settings import settings
        from langchain_openai import ChatOpenAI

        if not settings.deepseek_api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not configured. Set it in .env or the environment."
            )

        self._llm = ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=0.1,
        ).with_structured_output(LLMJudgeResult)

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(
        self,
        finding: dict[str, Any],
        rule: dict[str, Any] | None = None,
    ) -> LLMJudgeResult:
        """
        Analyze a single finding.

        `finding` – dict from `_finding_to_dict()` or Finding model fields.
        `rule`    – optional rule dict with `remediation`, `rationale`, etc.
        """
        prompt = self._build_prompt(finding, rule or {})
        log.debug("llm_judge_analyze", extra={"finding_id": finding.get("id")})
        result: LLMJudgeResult = self._llm.invoke(prompt)
        return result

    def analyze_batch(
        self,
        items: list[tuple[dict[str, Any], dict[str, Any] | None]],
    ) -> list[LLMJudgeResult | Exception]:
        """
        Analyze multiple (finding, rule) pairs sequentially.

        Returns a list of the same length as `items`, where each element is
        either an LLMJudgeResult or an Exception if that item failed.
        """
        results: list[LLMJudgeResult | Exception] = []
        for finding, rule in items:
            try:
                results.append(self.analyze(finding, rule))
            except Exception as exc:
                log.warning(
                    "llm_judge_batch_error",
                    extra={"finding_id": finding.get("id"), "error": str(exc)},
                )
                results.append(exc)
        return results

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(finding: dict[str, Any], rule: dict[str, Any]) -> str:
        platform = finding.get("platform", "unknown")
        severity = finding.get("severity", "unknown")
        category = finding.get("category", "")
        description = finding.get("description", "")
        resource = finding.get("resource_identifier", "")
        resource_type = finding.get("resource_type", "")
        evidence = finding.get("evidence", {})
        base_remediation = rule.get("remediation") or finding.get("remediation", "")
        rationale = rule.get("rationale", "")

        evidence_text = ""
        if evidence:
            evidence_lines = [f"  {k}: {v}" for k, v in list(evidence.items())[:10]]
            evidence_text = "\nEvidence:\n" + "\n".join(evidence_lines)

        return f"""You are a cloud security expert. A SSPM (SaaS Security Posture Management) system has detected a security finding. Analyze it carefully.

Platform: {platform}
Category: {category}
Current Severity: {severity}
Resource Type: {resource_type}
Resource: {resource}
Description: {description}
{f"Rationale: {rationale}" if rationale else ""}
{f"Original Remediation: {base_remediation}" if base_remediation else ""}
{evidence_text}

Your task:
1. Reassess the severity based on the specific context (consider the platform, resource type, and evidence).
2. Describe a realistic exploitation scenario — step by step, from attacker perspective.
3. Provide enhanced remediation steps specific to this finding and platform.
4. Rate your confidence in this assessment.

Be specific and actionable. Avoid generic advice.
"""


def apply_llm_result_to_finding(finding: Any, result: LLMJudgeResult) -> None:
    """
    Write LLM judge results back to a Finding ORM object in-place.
    Does NOT commit — caller is responsible for db.commit().
    """
    finding.llm_severity = result.severity
    finding.llm_severity_reasoning = result.severity_reasoning
    finding.llm_exploitability = result.exploitability
    finding.llm_remediation = result.remediation
    finding.llm_confidence = result.confidence
    finding.llm_analyzed_at = datetime.now(timezone.utc)
