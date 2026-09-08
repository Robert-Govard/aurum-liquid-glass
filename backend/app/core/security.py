"""Password hashing and JWT access/refresh token helpers.

bcrypt is used directly rather than through passlib — passlib's bcrypt
backend has been stuck on old pins and emits spurious "error reading
bcrypt version" warnings against bcrypt>=4, so this sidesteps that
entirely with one well-maintained dependency.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": "access", "iat": now, "exp": now + ACCESS_TOKEN_TTL}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Returns the user id encoded in a valid, unexpired access token.
    Raises jwt.PyJWTError (caught by callers, e.g. api/deps.py) if the
    token is invalid, expired, or not actually an access token."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return int(payload["sub"])


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """Returns (raw_jwt, sha256_hash_of_jwt, expires_at). Callers persist
    only the hash (see models/refresh_token.py) and hash whatever token a
    client presents later to compare against it — the raw JWT itself is
    never stored."""
    now = datetime.now(timezone.utc)
    expires_at = now + REFRESH_TOKEN_TTL
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, get_settings().jwt_secret, algorithm=JWT_ALGORITHM)
    return token, hash_token(token), expires_at


def decode_refresh_token(token: str) -> int:
    """Raises jwt.PyJWTError if invalid, expired, or not a refresh token.
    Does NOT check revocation — callers must additionally look up
    hash_token(token) in the refresh_tokens table (see
    services/auth_service.py:refresh)."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("not a refresh token")
    return int(payload["sub"])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
