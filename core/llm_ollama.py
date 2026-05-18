"""
core/llm_ollama.py — Contextual LLM remediation, impact scoring, and explanation via Ollama.

Configuration (all via environment variables):
  OLLAMA_URL       Base URL of the Ollama service  (default: http://ollama:11434)
  OLLAMA_MODEL     Model name                       (default: llama3.2)
  OLLAMA_TIMEOUT   Request timeout in seconds       (default: 120)
  OLLAMA_ENABLED   Set to "false" to disable all LLM calls (default: true)

Functions:
  generate_remediation(finding, posture_context) → str
  generate_impact_factor(finding, posture_context) → float
  generate_impact_explanation(finding, posture_context) → str

All functions:
  - Never include secrets, tokens, or credential values in prompts
  - Cache results in-process to avoid duplicate calls for the same finding
  - Fall back gracefully on timeout, connection error, or invalid output
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ── Config from env vars ──────────────────────────────────────────────────────
_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "30"))
_ENABLED = os.getenv("OLLAMA_ENABLED", "true").lower() not in ("false", "0", "no")

# ── In-process cache ──────────────────────────────────────────────────────────
# key → (result_str, timestamp)  — simple unbounded dict is fine for Phase 1
_CACHE: dict[str, str] = {}


def _cache_key(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{prefix}:{digest}"


# ── Secret scrubbing ──────────────────────────────────────────────────────────
_SCRUB_KEYS = frozenset({
    "token", "api_token", "api_key", "secret", "password", "credentials",
    "access_token", "refresh_token", "client_secret", "private_key",
})


def _scrub(obj: Any, depth: int = 0) -> Any:
    """Recursively remove secret-looking keys from dicts before sending to LLM."""
    if depth > 6:
        return obj
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if k.lower() in _SCRUB_KEYS else _scrub(v, depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub(item, depth + 1) for item in obj]
    return obj


# ── Low-level HTTP caller ─────────────────────────────────────────────────────

async def _generate(prompt: str) -> str:
    """POST /api/generate to Ollama. Raises on HTTP or connection error."""
    if not _ENABLED:
        raise RuntimeError("Ollama is disabled (OLLAMA_ENABLED=false)")

    payload = {
        "model": _MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
        },
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(f"{_OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()


# ── Prompt builders ───────────────────────────────────────────────────────────

def _safe_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Return a scrubbed, minimal finding dict safe to include in prompts."""
    safe = {k: finding[k] for k in (
        "id", "platform", "rule_id", "rule_name", "severity",
        "description", "resource_type", "resource_name", "resource_identifier",
        "category", "remediation",
    ) if k in finding}
    if "evidence" in finding:
        safe["evidence"] = _scrub(finding["evidence"])
    return safe


def _remediation_prompt(finding: dict[str, Any], ctx: dict[str, Any]) -> str:
    f = _safe_finding(finding)
    return f"""You are a SaaS security expert. A security misconfiguration was detected.
Provide a concise, actionable remediation in 3–5 bullet points.
Do NOT repeat the finding description. Focus only on the exact fix steps.

Finding:
- Platform: {f.get('platform', 'unknown')}
- Rule: {f.get('rule_name') or f.get('rule_id', '')}
- Severity: {f.get('severity', 'medium')}
- Description: {f.get('description', '')}
- Resource: {f.get('resource_name') or f.get('resource_identifier', '')}
- Evidence: {json.dumps(f.get('evidence', {}), default=str)}

Security context:
- Posture score: {ctx.get('posture_score', 'unknown')}
- Critical open findings: {ctx.get('critical_count', 0)}
- Affected platform user count: {ctx.get('user_count', 0)}

Remediation steps (bullet points only, no preamble):"""


def _impact_factor_prompt(finding: dict[str, Any], ctx: dict[str, Any]) -> str:
    f = _safe_finding(finding)
    return f"""You are a SaaS security risk analyst. Rate the impact of this finding on posture.

Finding: {f.get('rule_name') or f.get('rule_id')} — {f.get('severity')}
Description: {f.get('description', '')}
Platform: {f.get('platform')} | Resource: {f.get('resource_type')}
Evidence: {json.dumps(f.get('evidence', {}), default=str)}

Context: {ctx.get('critical_count', 0)} critical findings open, {ctx.get('user_count', 0)} users on platform.

Consider: blast radius, exploitability, privilege escalation risk, data sensitivity.

Reply with ONLY a decimal number 0.0 (no impact) to 1.0 (maximum impact). No explanation."""


def _impact_explanation_prompt(finding: dict[str, Any], ctx: dict[str, Any]) -> str:
    f = _safe_finding(finding)
    return f"""You are a SaaS security analyst explaining a misconfiguration to a security team.
Write 2–3 sentences explaining the POTENTIAL IMPACT of this finding.
Be specific about what an attacker could do, what data could be exposed, or what access could be gained.
Do NOT repeat the title. Do NOT give remediation steps.

Finding: {f.get('rule_name') or f.get('rule_id')} ({f.get('severity').upper()})
Platform: {f.get('platform')} | Resource type: {f.get('resource_type')}
Description: {f.get('description', '')}
Evidence: {json.dumps(f.get('evidence', {}), default=str)}
Posture score: {ctx.get('posture_score', 'unknown')}

Impact explanation (2–3 sentences, no preamble):"""


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_remediation(
    finding: dict[str, Any],
    posture_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """
    Generate a contextual remediation suggestion.

    Returns (text, source) where source is "ollama" or "static".
    Falls back to the static rule remediation on any error.
    """
    ctx = posture_context or {}
    ckey = _cache_key("rem", finding.get("id"), finding.get("rule_id"), finding.get("resource_identifier"))

    if ckey in _CACHE:
        return _CACHE[ckey], "ollama"

    try:
        text = await _generate(_remediation_prompt(finding, ctx))
        _CACHE[ckey] = text
        return text, "ollama"
    except Exception as exc:
        log.warning("Ollama remediation failed for finding %s: %s", finding.get("id"), exc)
        fallback = finding.get("remediation") or "See rule documentation for remediation guidance."
        return fallback, "static"


async def generate_impact_factor(
    finding: dict[str, Any],
    posture_context: dict[str, Any] | None = None,
) -> float:
    """
    Score the impact of a finding (0.0–1.0). Falls back to 0.5.
    """
    ctx = posture_context or {}
    ckey = _cache_key("imp", finding.get("id"), finding.get("rule_id"), finding.get("resource_identifier"))

    if ckey in _CACHE:
        try:
            return float(_CACHE[ckey])
        except ValueError:
            pass

    try:
        raw = await _generate(_impact_factor_prompt(finding, ctx))
        for token in raw.split():
            try:
                val = float(token.strip(".,;"))
                result = max(0.0, min(1.0, val))
                _CACHE[ckey] = str(result)
                return result
            except ValueError:
                continue
        log.warning("Could not parse impact factor from: %r", raw)
    except Exception as exc:
        log.warning("Ollama impact factor failed for finding %s: %s", finding.get("id"), exc)
    return 0.5


async def generate_impact_explanation(
    finding: dict[str, Any],
    posture_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """
    Generate a 2–3 sentence impact explanation.

    Returns (text, source) where source is "ollama" or "static".
    """
    ctx = posture_context or {}
    ckey = _cache_key("expl", finding.get("id"), finding.get("rule_id"), finding.get("resource_identifier"))

    if ckey in _CACHE:
        return _CACHE[ckey], "ollama"

    try:
        text = await _generate(_impact_explanation_prompt(finding, ctx))
        _CACHE[ckey] = text
        return text, "ollama"
    except Exception as exc:
        log.warning("Ollama impact explanation failed for finding %s: %s", finding.get("id"), exc)
        sev = finding.get("severity", "medium")
        desc = finding.get("description", "")
        fallback = f"This {sev}-severity misconfiguration ({desc}) may expose the organization to unauthorized access or data compromise."
        return fallback, "static"
