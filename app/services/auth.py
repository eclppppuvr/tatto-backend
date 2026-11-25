"""INT-1, INT-2, INT-3, INT-7: регистрация, вход, ротация refresh, выход."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID, uuid4

from ..config import Settings
from ..domain.entities import RefreshToken, Role, User
from ..domain.errors import (AccountBlocked, EmailTaken, InvalidCredentials, InvalidRefreshToken,
                             RevokedRefreshToken)
from ..domain.ports import PasswordHasher, RefreshTokenRepo, UserRepo
from ..rate_limit import LoginRateLimiter
from ..security import create_access_token, hash_refresh_token, new_refresh_token


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, users: UserRepo, tokens: RefreshTokenRepo, hasher: PasswordHasher,
                 settings: Settings, limiter: LoginRateLimiter | None = None,
                 clock: Callable[[], datetime] = utcnow):
        self._users = users
        self._tokens = tokens
        self._hasher = hasher
        self._settings = settings
        self._limiter = limiter
        self._clock = clock
        self._dummy_hash: str | None = None

    # --- INT-1 ---
    def register(self, email: str, password: str) -> tuple[User, TokenPair]:
        email = normalize_email(email)
        if self._users.get_by_email(email):
            raise EmailTaken()
        now = self._clock()
        user = self._users.add(User(
            id=uuid4(), email=email, hashed_password=self._hasher.hash(password),
            role=Role.CLIENT, is_active=True, created_at=now, updated_at=now,
        ))
        return user, self._issue(user)

    # --- INT-2 ---
    def login(self, email: str, password: str, client_ip: str = "unknown") -> tuple[User, TokenPair]:
        if self._limiter:
            self._limiter.check(client_ip)
        user = self._users.get_by_email(normalize_email(email))
        # Проверяем хеш и для несуществующего email — одинаковое время ответа.
        password_ok = self._hasher.verify(password, user.hashed_password if user else self._get_dummy_hash())
        if user is None or not password_ok:
            if self._limiter:
                self._limiter.fail(client_ip)
            raise InvalidCredentials()
        if not user.is_active:
            raise AccountBlocked()
        if self._limiter:
            self._limiter.reset(client_ip)
        return user, self._issue(user)

    # --- INT-3 ---
    def refresh(self, raw_refresh_token: str) -> TokenPair:
        record = self._tokens.get_by_hash(hash_refresh_token(raw_refresh_token))
        if record is None:
            raise InvalidRefreshToken()
        if record.revoked:
            raise RevokedRefreshToken()
        if record.expires_at <= self._clock():
            raise InvalidRefreshToken()
        user = self._users.get_by_id(record.user_id)
        if user is None:
            raise InvalidRefreshToken()
        if not user.is_active:
            raise AccountBlocked()
        # Ротация: старый токен аннулируется атомарно, параллельное повторное использование не пройдёт.
        if not self._tokens.revoke(record.id):
            raise RevokedRefreshToken()
        return self._issue(user)

    # --- INT-7 ---
    def logout(self, user_id: UUID, raw_refresh_token: str | None) -> None:
        if not raw_refresh_token:
            return
        record = self._tokens.get_by_hash(hash_refresh_token(raw_refresh_token))
        if record and record.user_id == user_id and not record.revoked:
            self._tokens.revoke(record.id)

    # --- helpers ---
    def _issue(self, user: User) -> TokenPair:
        now = self._clock()
        raw = new_refresh_token()
        self._tokens.add(RefreshToken(
            id=uuid4(), user_id=user.id, token_hash=hash_refresh_token(raw),
            expires_at=now + timedelta(days=self._settings.refresh_ttl_days),
            revoked=False, created_at=now,
        ))
        access = create_access_token(user.id, user.role, self._settings.jwt_secret,
                                     self._settings.access_ttl_minutes, now)
        return TokenPair(access_token=access, refresh_token=raw)

    def _get_dummy_hash(self) -> str:
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash("dummy-password-for-timing")
        return self._dummy_hash
