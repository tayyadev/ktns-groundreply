"""Password hashes, signed sessions, anti-CSRF and one-time invite tokens."""
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import HTTPException

from app.config import get_settings

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
ISSUER = "ktns-groundreply"
AUDIENCE = "groundreply-web"


def validate_secret() -> None:
    secret = get_settings().jwt_secret
    if len(secret) < 32 or secret.startswith("REPLACE_"):
        raise RuntimeError("Set JWT_SECRET to a random string of 32+ characters in .env")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def new_session_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id), "jti": str(uuid.uuid4()), "iss": ISSUER, "aud": AUDIENCE,
            "iat": now, "exp": now + timedelta(hours=12),
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )


def decode_session(token: str) -> dict:
    try:
        return jwt.decode(
            token, get_settings().jwt_secret,
            algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER,
            options={"require": ["exp", "sub", "jti", "iat", "iss", "aud"]},
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Session expired or invalid") from exc


def csrf_token(payload: dict) -> str:
    value = f"{payload['sub']}:{payload['jti']}".encode()
    return hmac.new(get_settings().jwt_secret.encode(), value, hashlib.sha256).hexdigest()


def check_csrf(payload: dict, provided: str | None) -> None:
    if not provided or not hmac.compare_digest(csrf_token(payload), provided):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def make_invite_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(36)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def invite_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    organization_name: str
    role: str
    plan: str
    token_claims: dict
