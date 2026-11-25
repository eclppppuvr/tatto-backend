"""Пароли, JWT access-токены, opaque refresh-токены."""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import jwt

from .domain.entities import Role
from .domain.errors import InvalidAccessToken

JWT_ALGORITHM = "HS256"


class BcryptHasher:
    """bcrypt (cost из настроек). Пароль предварительно сворачивается в SHA-256 + base64:
    так нет усечения на 72 байтах и ошибки на длинных паролях."""

    def __init__(self, rounds: int = 12):
        self.rounds = rounds

    @staticmethod
    def _prepare(password: str) -> bytes:
        return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())

    def hash(self, password: str) -> str:
        import bcrypt

        return bcrypt.hashpw(self._prepare(password), bcrypt.gensalt(self.rounds)).decode("ascii")

    def verify(self, password: str, hashed: str) -> bool:
        import bcrypt

        try:
            return bcrypt.checkpw(self._prepare(password), hashed.encode("ascii"))
        except ValueError:
            return False


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    role: Role


def create_access_token(user_id: UUID, role: Role, secret: str, ttl_minutes: int, now: datetime) -> str:
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token, secret, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub", "type"]}
        )
        if payload["type"] != "access":
            raise InvalidAccessToken()
        return AccessClaims(user_id=UUID(payload["sub"]), role=Role(payload.get("role", "client")))
    except (jwt.PyJWTError, ValueError, KeyError):
        raise InvalidAccessToken() from None


def new_refresh_token() -> str:
    return "rt_" + secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """В БД хранится только SHA-256 (TB-02 §5.3)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
