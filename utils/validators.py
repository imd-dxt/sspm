"""Input validation helpers used across the codebase."""
import re


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
_PLATFORM_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value or ""))


def is_valid_platform_name(value: str) -> bool:
    """Platform names are lowercase alphanumeric with dashes/underscores, max 64 chars."""
    return bool(_PLATFORM_RE.match(value or ""))


def sanitize_string(value: str, max_length: int = 1024) -> str:
    """Strip leading/trailing whitespace and truncate to max_length."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]
