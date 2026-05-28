"""
api/auth.py — JWT creation and verification dependency.

Usage in routes:
    from api.auth import CurrentUser

    @router.get("/protected")
    def protected(user: CurrentUser) -> dict:
        return {"user": user}
"""
from __future__ import annotations

import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from config.settings import settings

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)


def _resolve_jwt_secret() -> str:
    if settings.jwt_secret:
        return settings.jwt_secret
    generated = secrets.token_hex(32)
    log.warning(
        "JWT_SECRET not set — using an auto-generated secret. "
        "Tokens will be invalidated on every restart. "
        "Set JWT_SECRET in .env for persistent sessions."
    )
    return generated


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
