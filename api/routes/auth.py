"""
/auth  — Login and session info.

Endpoints:
  POST /auth/login   – exchange credentials for a JWT access token
  GET  /auth/me      – return the current authenticated user (token validation)
"""
from __future__ import annotations

import logging
import secrets
import string

from fastapi import APIRouter, HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel

from api.auth import CurrentUser, create_access_token
from config.settings import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _resolve_admin_hash() -> str:
    """
    Resolve the admin password hash at startup.
    Priority: ADMIN_PASSWORD_HASH > ADMIN_PASSWORD > auto-generated random password.
    """
    if settings.admin_password_hash:
        return settings.admin_password_hash

    if settings.admin_password:
        log.warning(
            "ADMIN_PASSWORD set as plain text. "
            "Consider switching to ADMIN_PASSWORD_HASH for better security."
        )
        return _pwd_ctx.hash(settings.admin_password)

    # Neither hash nor password provided — generate a one-time password and log it.
    alphabet = string.ascii_letters + string.digits
    random_pwd = "".join(secrets.choice(alphabet) for _ in range(20))
    log.warning("=" * 68)
    log.warning("ADMIN PASSWORD NOT CONFIGURED — auto-generated for this session:")
    log.warning("  Username : %s", settings.admin_username)
    log.warning("  Password : %s", random_pwd)
    log.warning("Set ADMIN_PASSWORD or ADMIN_PASSWORD_HASH in your .env file.")
    log.warning("This password changes on every restart until you configure one.")
    log.warning("=" * 68)
    return _pwd_ctx.hash(random_pwd)


_ADMIN_HASH: str = _resolve_admin_hash()


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    expires_in: int  # seconds


class MeResponse(BaseModel):
    username: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    """Authenticate with admin credentials and receive a JWT access token."""
    credentials_ok = (
        req.username == settings.admin_username
        and _pwd_ctx.verify(req.password, _ADMIN_HASH)
    )
    if not credentials_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(req.username)
    return TokenResponse(
        access_token=token,
        username=req.username,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> MeResponse:
    """Return the username of the currently authenticated user."""
    return MeResponse(username=user)
