"""Интерфейсы хранилищ. Реализации: app/db/repos.py (PostgreSQL), позже MongoDB для эскизов."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .entities import Job, Profile, RefreshToken, SketchSummary, User


class UserRepo(Protocol):
    def get_by_email(self, email: str) -> User | None: ...
    def get_by_id(self, user_id: UUID) -> User | None: ...
    def add(self, user: User) -> User:
        """Бросает EmailTaken при дубликате email."""


class ProfileRepo(Protocol):
    def get(self, user_id: UUID) -> Profile | None: ...
    def upsert(self, user_id: UUID, patch: dict) -> Profile: ...


class RefreshTokenRepo(Protocol):
    def add(self, token: RefreshToken) -> None: ...
    def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...
    def revoke(self, token_id: UUID) -> bool:
        """Атомарно помечает токен отозванным. False — если уже был отозван."""


class SketchRepo(Protocol):
    def list_by_user(self, user_id: UUID, page: int, limit: int) -> tuple[list[SketchSummary], int]: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, hashed: str) -> bool: ...


class JobRepo(Protocol):
    def add(self, job: Job) -> Job: ...
    def get(self, job_id: UUID) -> Job | None: ...
    def save(self, job: Job) -> Job:
        """Сохраняет изменяемые поля (статус, прогресс, результат, ошибки, время)."""


class EventPublisher(Protocol):
    def publish(self, job: Job) -> None:
        """Best-effort: сбой доставки не должен ронять обработку (есть polling-fallback)."""


class JobDispatcher(Protocol):
    def dispatch(self, job: Job) -> None:
        """Ставит job в очередь. Вызывать только ПОСЛЕ коммита транзакции."""
