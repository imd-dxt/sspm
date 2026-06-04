"""
/auth  — Login, session info, and configuration diagnostics.

Endpoints:
  POST /auth/login   – exchange credentials for a JWT access token
  GET  /auth/me      – return the current authenticated user (token validation)
  GET  /auth/info    – PUBLIC: shows which credential source is active (no secrets)
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


# ── Admin credential resolution at startup ───────────────────────────────────

def _resolve_admin_credentials() -> tuple[str, str]:
    """
    Returns (hash, source) where source is one of:
      'env_hash'    — from ADMIN_PASSWORD_HASH
      'env_password' — from ADMIN_PASSWORD (hashed at startup)
      'auto_generated' — random password (printed to logs, changes on restart)
    """
    if settings.admin_password_hash:
        log.info("admin credentials: using ADMIN_PASSWORD_HASH from env")
        return settings.admin_password_hash, "env_hash"

    if settings.admin_password:
        log.info("admin credentials: using ADMIN_PASSWORD from env (hashing at startup)")
        return _pwd_ctx.hash(settings.admin_password), "env_password"

    # Neither hash nor password provided — generate a one-time password.
    alphabet = string.ascii_letters + string.digits
    random_pwd = "".join(secrets.choice(alphabet) for _ in range(20))
    log.warning("=" * 68)
    log.warning("ADMIN PASSWORD NOT CONFIGURED — auto-generated for this session:")
    log.warning("  Username : %s", settings.admin_username)
    log.warning("  Password : %s", random_pwd)
    log.warning("Set ADMIN_PASSWORD or ADMIN_PASSWORD_HASH in your .env file.")
    log.warning("This password changes on every restart until you configure one.")
    log.warning("=" * 68)
    return _pwd_ctx.hash(random_pwd), "auto_generated"


_ADMIN_HASH, _ADMIN_SOURCE = _resolve_admin_credentials()
log.info("auth ready — username=%s, source=%s", settings.admin_username, _ADMIN_SOURCE)


def _verify_password(plain: str, hashed: str) -> bool:
    """
    Wrapper around bcrypt.verify() that swallows internal errors.
    passlib + bcrypt 4.x can raise ValueError on hashes from older bcrypt
    versions — we treat any verify exception as 'password does not match'.
    """
    try:
        return _pwd_ctx.verify(plain, hashed)
    except Exception as exc:  # bcrypt/passlib compatibility issues
        log.warning("password verification raised exception: %s", exc)
        return False


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


class AuthInfoResponse(BaseModel):
    configured_username: str
    credential_source: str  # 'env_hash' | 'env_password' | 'auto_generated'
    jwt_secret_persistent: bool
    jwt_expire_minutes: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    """Authenticate with admin credentials and receive a JWT access token."""
    username_ok = req.username == settings.admin_username
    password_ok = _verify_password(req.password, _ADMIN_HASH)

    if not (username_ok and password_ok):
        log.info(
            "login_failed user=%s username_match=%s password_match=%s",
            req.username, username_ok, password_ok,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(req.username)
    log.info("login_success user=%s", req.username)
    return TokenResponse(
        access_token=token,
        username=req.username,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> MeResponse:
    """Return the username of the currently authenticated user."""
    return MeResponse(username=user)


@router.get("/info", response_model=AuthInfoResponse)
def auth_info() -> AuthInfoResponse:
    """
    PUBLIC endpoint for diagnostics — confirms which admin username and
    credential source the API resolved at startup. Returns no secrets.

    Use this to verify your .env is reaching the container:
      curl http://localhost/api/v1/auth/info
    """
    return AuthInfoResponse(
        configured_username=settings.admin_username,
        credential_source=_ADMIN_SOURCE,
        jwt_secret_persistent=bool(settings.jwt_secret),
        jwt_expire_minutes=settings.jwt_expire_minutes,
    )
