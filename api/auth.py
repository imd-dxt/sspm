"""
api/auth.py — JWT creation and verification dependency.

Usage in routes:
    from api.auth import CurrentUser

    @router.get("/protected")
    def protected(user: CurrentUser) -> dict:
        return {"user": user}
"""
from __future__ import annotations

import os
import secrets
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from config.settings import settings

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)

# Shared file location so concurrent uvicorn workers agree on the same
# auto-generated secret. Kept inside the container's app dir (not /tmp) to
# avoid sharing a world-writable directory.
_JWT_SECRET_FILE = Path("/app/.jwt_secret")


def _resolve_jwt_secret() -> str:
    """
    Resolution order:
      1. JWT_SECRET env var (preferred — persists across restarts)
      2. Shared file /tmp/sspm_jwt_secret (lets multi-worker uvicorn agree)
      3. Generate a new secret, write atomically to the shared file
    """
    if settings.jwt_secret:
        log.info("JWT_SECRET loaded from environment (persistent across restarts)")
        return settings.jwt_secret

    # Try to read an existing shared secret (another worker may have written it)
    try:
        if _JWT_SECRET_FILE.exists():
            existing = _JWT_SECRET_FILE.read_text().strip()
            if existing:
                log.info("JWT_SECRET loaded from shared file %s", _JWT_SECRET_FILE)
                return existing
    except OSError as exc:
        log.warning("Could not read %s: %s", _JWT_SECRET_FILE, exc)

    # Atomically create the file with our secret. If another worker beats us
    # (FileExistsError), read its value instead so all workers agree.
    generated = secrets.token_hex(32)
    try:
        fd = os.open(str(_JWT_SECRET_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(generated)
        log.warning("=" * 68)
        log.warning("JWT_SECRET not set in environment — generated one for this container.")
        log.warning("Secret persisted to %s and shared across uvicorn workers.", _JWT_SECRET_FILE)
        log.warning("Tokens WILL be invalidated when the container restarts.")
        log.warning("Set JWT_SECRET in .env for tokens that survive restarts:")
        log.warning("    openssl rand -hex 32")
        log.warning("=" * 68)
        return generated
    except FileExistsError:
        # Another worker raced us — use whatever it wrote.
        existing = _JWT_SECRET_FILE.read_text().strip()
        log.info("Another worker wrote JWT_SECRET first — using its value")
        return existing


_JWT_SECRET: str = _resolve_jwt_secret()


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": username, "exp": expire},
        _JWT_SECRET,
        algorithm=settings.jwt_algorithm,
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> str:
    """FastAPI dependency — validates the Bearer token and returns the username."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            _JWT_SECRET,
            algorithms=[settings.jwt_algorithm],
        )
        username: str | None = payload.get("sub")
        if not username:
            raise ValueError("missing sub claim")
        return username
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


CurrentUser = Annotated[str, Depends(get_current_user)]
