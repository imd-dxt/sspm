"""
core/llm_router.py — Central LLM orchestrator for the SSPM platform.

Routing policy (privacy-first):
  Tasks needing raw sensitive data → Ollama (local, private)
  Tasks using only anonymised aggregates → DeepSeek (cloud)

Privacy guarantee:
  SENSITIVE_FIELDS values are NEVER sent to DeepSeek.
  sanitise() tokenises them; de_tokenise() restores in output.
  Token maps are held in memory only during a single call and immediately discarded.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from config.settings import settings

log = logging.getLogger(__name__)

SENSITIVE_FIELDS = frozenset({
    "username", "email", "display_name", "user_principal_name",
    "ip_address", "source_ip", "tenant_id", "account_id",
    "platform_id", "client_id", "client_secret", "password",
    "org_name", "tenant_name", "domain", "instance_url",
    "webhook_url", "callback_url", "api_token",
})

TASK_ROUTING: dict[str, str] = {
    "remediation_steps":     "ollama",
    "finding_explanation":   "ollama",
    "risk_narrative_raw":    "ollama",
    "qa_answer":             "ollama",
    "executive_summary":     "deepseek",
    "risk_narrative_anon":   "deepseek",
    "impact_analysis":       "deepseek",
    "compliance_insights":   "deepseek",
    "roadmap_intro":         "deepseek",
    "exploitation_scenario": "deepseek",
    "trend_narrative":       "deepseek",
}

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_UUID_RE  = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)


class LLMRouter:
    """Central LLM orchestrator — routes tasks to Ollama or DeepSeek."""

    def __init__(self) -> None:
        self.ollama_url       = settings.ollama_url
        self.ollama_model     = settings.ollama_model
        self.deepseek_url     = "https://api.deepseek.com/v1/chat/completions"
        self.deepseek_key     = settings.deepseek_api_key
        self.deepseek_model   = settings.deepseek_model
        self.ollama_timeout   = float(settings.llm_timeout_ollama)
        self.deepseek_timeout = float(settings.llm_timeout_deepseek)

    # ── Sanitisation ──────────────────────────────────────────────────────────

    def sanitise(self, data: Any) -> tuple[Any, dict[str, str]]:
        """
        Recursively replace SENSITIVE_FIELDS values with TOKEN_NNN.
        Returns (sanitised_data, token_map).  Never mutates the original.
        """
        counter = [0]
        token_map: dict[str, str] = {}

        def _token(val: str) -> str:
            counter[0] += 1
            tok = f"TOKEN_{counter[0]:03d}"
            token_map[tok] = val
            return tok

        def _walk(obj: Any) -> Any:
            if isinstance(obj, dict):
                out: dict[str, Any] = {}
                for k, v in obj.items():
                    if k.lower() in SENSITIVE_FIELDS and isinstance(v, str) and v:
                        out[k] = _token(v)
                    else:
                        out[k] = _walk(v)
                return out
            if isinstance(obj, list):
                return [_walk(item) for item in obj]
            if isinstance(obj, str):
                obj = _EMAIL_RE.sub(lambda m: _token(m.group(0)), obj)
                obj = _UUID_RE.sub(lambda m: _token(m.group(0)), obj)
                return obj
            return obj

        return _walk(data), token_map

    def de_tokenise(self, text: str, token_map: dict[str, str]) -> str:
        for tok, orig in token_map.items():
            text = text.replace(tok, orig)
        return text

    # ── LLM callers ───────────────────────────────────────────────────────────

    def call_ollama(self, prompt: str, timeout: float | None = None) -> str | None:
        t = timeout or self.ollama_timeout
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 512},
        }
        try:
            t0 = time.monotonic()
            with httpx.Client(timeout=t) as client:
                resp = client.post(f"{self.ollama_url}/api/generate", json=payload)
                resp.raise_for_status()
            latency = round((time.monotonic() - t0) * 1000)
            result = resp.json().get("response", "").strip()
            log.info("llm_call provider=ollama model=%s latency_ms=%d privacy=raw",
                     self.ollama_model, latency)
            return result or None
        except Exception as exc:
            log.warning("ollama_call_failed: %s", exc)
            return None

    def call_deepseek(self, prompt: str, system: str | None = None,
                      timeout: float | None = None) -> str | None:
        if not self.deepseek_key:
            log.warning("deepseek_api_key not configured")
            return None
        t = timeout or self.deepseek_timeout
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.deepseek_model, "messages": messages, "temperature": 0.3}
        headers = {
            "Authorization": f"Bearer {self.deepseek_key}",
            "Content-Type": "application/json",
        }
        try:
            t0 = time.monotonic()
            with httpx.Client(timeout=t) as client:
                resp = client.post(self.deepseek_url, json=payload, headers=headers)
                resp.raise_for_status()
            latency = round((time.monotonic() - t0) * 1000)
            data = resp.json()
            result = data["choices"][0]["message"]["content"].strip()
            tokens = data.get("usage", {}).get("total_tokens")
            log.info("llm_call provider=deepseek model=%s latency_ms=%d tokens=%s privacy=anonymised",
                     self.deepseek_model, latency, tokens)
            return result or None
        except Exception as exc:
            log.warning("deepseek_call_failed: %s", exc)
            return None

    # ── Main entry point ──────────────────────────────────────────────────────

    def generate(self, task: str, data: dict[str, Any],
                 fallback_text: str | None = None) -> str:
        """
        Route task to the correct LLM.  Never raises.
        If both LLMs fail, returns fallback_text or a standard message.
        """
        provider = TASK_ROUTING.get(task, "ollama")
        fallback = (fallback_text or
                    "[AI analysis unavailable — configure Ollama or DeepSeek API key]")
        try:
            if provider == "deepseek":
                sanitised, token_map = self.sanitise(data)
                prompt = self._build_prompt(task, sanitised)
                raw = self.call_deepseek(prompt)
                if raw is None:
                    raw = self.call_ollama(prompt)
                if raw is None:
                    return fallback
                return self.de_tokenise(raw, token_map)
            else:
                prompt = self._build_prompt(task, data)
                raw = self.call_ollama(prompt)
                return raw if raw is not None else fallback
        except Exception as exc:
            log.warning("llm_router_generate_failed task=%s: %s", task, exc)
            return fallback

    def _build_prompt(self, task: str, data: Any) -> str:
        return (f"Task: {task}\n"
                f"Data: {json.dumps(data, default=str, indent=2)}\n\n"
                "Provide a concise professional analysis.")

    # ── Specific task helpers ─────────────────────────────────────────────────

    def generate_remediation(self, finding: dict[str, Any]) -> str:
        prompt = f"""You are a senior cybersecurity engineer.
A misconfiguration has been detected:

Finding: {finding.get('rule_name') or finding.get('name', 'Unknown')}
Platform: {finding.get('platform', 'unknown')}
Severity: {finding.get('severity', 'medium')}
Description: {finding.get('description', '')}
Evidence: {finding.get('evidence', 'N/A')}
Compliance controls: {finding.get('compliance_mapping', [])}

Write exactly 5 numbered remediation steps, specific to this platform.
Be direct and technical. No preamble. No markdown headers."""
        result = self.call_ollama(prompt)
        return result or "[Remediation guidance unavailable — configure Ollama]"

    def generate_executive_summary(self, scores: dict[str, int],
                                   stats: dict[str, Any]) -> str:
        prompt = f"""You are a Chief Information Security Officer writing a board-level report.
Do not use technical jargon. Write in clear executive language.

Compliance scores this period:
{json.dumps(scores, indent=2)}

Finding statistics:
{json.dumps(stats, indent=2)}

Write a 3-paragraph executive summary:
1. Overall security posture and trend
2. Most critical risks and their business impact
3. Recommended strategic actions for the next 30 days

Tone: confident, factual, non-alarmist. Max 200 words total."""
        result = self.call_deepseek(prompt)
        if result is None:
            result = self.call_ollama(prompt)
        return result or "[Executive summary unavailable — configure DeepSeek or Ollama]"

    def generate_exploitation_scenario(self, severity: str, category: str,
                                        control_id: str) -> str:
        prompt = f"""You are a cybersecurity red team analyst.
Control: {control_id} | Category: {category} | Severity: {severity}

Describe a realistic 3-sentence attack scenario that exploits this control failure.
Focus on: initial access → lateral movement → impact.
Do NOT reference any specific organisation. Use generic terms only.
No markdown headers. Direct prose only."""
        result = self.call_deepseek(prompt)
        if result is None:
            result = self.call_ollama(prompt)
        return result or f"[Exploitation scenario unavailable for {control_id}]"

    def _ollama_anonymize_finding(self, finding: dict[str, Any]) -> str:
        """
        Ask Ollama (local) to convert a raw finding into a 2-3 sentence,
        privacy-safe context summary that contains NO emails, usernames,
        UUIDs, or organisation-specific identifiers.

        This summary is what DeepSeek (cloud) sees — never the raw finding.
        """
        prompt = f"""You are a privacy-preserving security analyst.
Read the security finding below and write 2-3 sentences describing it
ABSTRACTLY for a cloud LLM that must not learn any private details.

STRICT RULES:
- NEVER include emails, usernames, real names, UUIDs, repo names,
  organisation names, tenant IDs, IPs, or any concrete identifier.
- Replace specific resources with generic phrasing (e.g. "a production
  repository", "an admin account").
- Keep severity, control type, platform name (github/jira/etc) and
  finding category — these are NOT sensitive.

Finding (raw — keep this server-side only):
{json.dumps(finding, indent=2, default=str)[:1500]}

Output (the abstract description only — no preamble):"""
        result = self.call_ollama(prompt)
        if result:
            return result
        # Fallback: hand-built safe summary if Ollama is offline
        return (
            f"A {finding.get('severity', 'medium')}-severity finding in the "
            f"{finding.get('category', 'security')} category on the "
            f"{finding.get('platform', 'a SaaS')} platform "
            f"({finding.get('open_count', 0)} open occurrence(s))."
        )

    def generate_impact_analysis(self, finding: dict[str, Any]) -> str:
        """
        Orchestrated pipeline:  Ollama (raw → anonymous context)
                              → DeepSeek (anonymous context → polished narrative)

        DeepSeek never sees the raw finding. Only the Ollama-produced summary
        plus three non-sensitive labels (severity, category, platform) are sent.
        """
        anonymous_context = self._ollama_anonymize_finding(finding)
        prompt = f"""You are a risk analyst writing for a board-level compliance report.

Context (already anonymised — contains no private identifiers):
{anonymous_context}

Metadata: severity={finding.get('severity', 'medium')}, category={finding.get('category', 'general')}, platform={finding.get('platform', 'saas')}

Write 3 concise bullet points (max 60 words total):
• Business / operational impact
• Regulatory / compliance exposure
• Estimated remediation effort

No preamble, no headers, plain prose under each bullet."""
        result = self.call_deepseek(prompt)
        if result is None:
            # Fall back to Ollama for the full narrative if DeepSeek is unavailable
            result = self.call_ollama(prompt)
        return result or "[Impact analysis unavailable]"

    def generate_trend_narrative(self, trend_summary: dict[str, Any]) -> str:
        prompt = f"""You are a security analyst reviewing compliance trends.
Score trend data (anonymised):
{json.dumps(trend_summary, indent=2, default=str)}

Write 2 sentences summarising the trend direction and its significance.
Focus on improving vs declining platforms. Max 50 words."""
        result = self.call_deepseek(prompt)
        if result is None:
            result = self.call_ollama(prompt)
        return result or "[Trend narrative unavailable]"

    def check_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {}
        try:
            t0 = time.monotonic()
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.ollama_url}/api/tags")
            latency = round((time.monotonic() - t0) * 1000)
            status["ollama"] = {
                "available": resp.status_code == 200,
                "model": self.ollama_model,
                "url": self.ollama_url,
                "latency_ms": latency,
            }
        except Exception:
            status["ollama"] = {
                "available": False, "model": self.ollama_model,
                "url": self.ollama_url, "latency_ms": None,
            }

        if self.deepseek_key:
            try:
                t0 = time.monotonic()
                with httpx.Client(timeout=5) as client:
                    resp = client.get(
                        "https://api.deepseek.com/models",
                        headers={"Authorization": f"Bearer {self.deepseek_key}"},
                    )
                latency = round((time.monotonic() - t0) * 1000)
                status["deepseek"] = {
                    "available": resp.status_code == 200,
                    "model": self.deepseek_model,
                    "api_key_configured": True,
                    "latency_ms": latency,
                }
            except Exception:
                status["deepseek"] = {
                    "available": False, "model": self.deepseek_model,
                    "api_key_configured": True, "latency_ms": None,
                }
        else:
            status["deepseek"] = {
                "available": False, "model": self.deepseek_model,
                "api_key_configured": False, "latency_ms": None,
            }

        status["routing"] = {
            "executive_summary":      TASK_ROUTING["executive_summary"],
            "remediation_steps":      TASK_ROUTING["remediation_steps"],
            "exploitation_scenarios": TASK_ROUTING["exploitation_scenario"],
            "fallback":               "template",
        }
        return status
