"""Реализации портов на SQLAlchemy. Коммит делает зависимость сессии (app/db/session.py)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.entities import Job, Profile, RefreshToken, User
from ..domain.errors import EmailTaken
from .models import JobRow, ProfileRow, RefreshTokenRow, UserRow


def _aware(dt: datetime) -> datetime:
    """SQLite отдаёт naive datetime; в PostgreSQL значения уже с tz."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _user(row: UserRow) -> User:
    return User(row.id, row.email, row.hashed_password, row.role, row.is_active,
                _aware(row.created_at), _aware(row.updated_at))


def _profile(row: ProfileRow) -> Profile:
    return Profile(row.user_id, row.display_name, row.avatar_s3_key, row.bio, dict(row.preferences or {}))


def _token(row: RefreshTokenRow) -> RefreshToken:
    return RefreshToken(row.id, row.user_id, row.token_hash, _aware(row.expires_at), row.revoked,
                        _aware(row.created_at))


class SqlUserRepo:
    def __init__(self, session: Session):
        self._s = session

    def get_by_email(self, email: str) -> User | None:
        row = self._s.scalar(select(UserRow).where(UserRow.email == email))
        return _user(row) if row else None

    def get_by_id(self, user_id: UUID) -> User | None:
        row = self._s.get(UserRow, user_id)
        return _user(row) if row else None

    def add(self, user: User) -> User:
        self._s.add(UserRow(id=user.id, email=user.email, hashed_password=user.hashed_password,
                            role=user.role, is_active=user.is_active,
                            created_at=user.created_at, updated_at=user.updated_at))
        try:
            self._s.flush()
        except IntegrityError:
            raise EmailTaken() from None  # гонка двух регистраций; сессия откатится выше по стеку
        return user


class SqlProfileRepo:
    def __init__(self, session: Session):
        self._s = session

    def get(self, user_id: UUID) -> Profile | None:
        row = self._s.get(ProfileRow, user_id)
        return _profile(row) if row else None

    def upsert(self, user_id: UUID, patch: dict) -> Profile:
        row = self._s.get(ProfileRow, user_id)
        if row is None:
            row = ProfileRow(user_id=user_id, preferences={})
            self._s.add(row)
        for key, value in patch.items():
            setattr(row, key, value)
        self._s.flush()
        return _profile(row)


class SqlRefreshTokenRepo:
    def __init__(self, session: Session):
        self._s = session

    def add(self, token: RefreshToken) -> None:
        self._s.add(RefreshTokenRow(id=token.id, user_id=token.user_id, token_hash=token.token_hash,
                                    expires_at=token.expires_at, revoked=token.revoked,
                                    created_at=token.created_at))
        self._s.flush()

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        row = self._s.scalar(select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash))
        return _token(row) if row else None

    def revoke(self, token_id: UUID) -> bool:
        result = self._s.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.id == token_id, RefreshTokenRow.revoked.is_(False))
            .values(revoked=True)
        )
        return result.rowcount == 1


def _opt_aware(dt: datetime | None) -> datetime | None:
    return _aware(dt) if dt else None


def _job(row: JobRow) -> Job:
    return Job(row.id, row.user_id, row.type, row.status, row.progress, row.input_ref, row.output_ref,
               row.error_code, row.error_message, row.retry_count, _aware(row.created_at),
               _aware(row.updated_at), _opt_aware(row.started_at), _opt_aware(row.finished_at))


class SqlJobRepo:
    _MUTABLE = ("status", "progress", "output_ref", "error_code", "error_message", "retry_count",
                "updated_at", "started_at", "finished_at")

    def __init__(self, session: Session):
        self._s = session

    def add(self, job: Job) -> Job:
        self._s.add(JobRow(
            id=job.id, user_id=job.user_id, type=job.type, status=job.status, progress=job.progress,
            input_ref=job.input_ref, output_ref=job.output_ref, error_code=job.error_code,
            error_message=job.error_message, retry_count=job.retry_count, created_at=job.created_at,
            updated_at=job.updated_at, started_at=job.started_at, finished_at=job.finished_at,
        ))
        self._s.flush()
        return job

    def get(self, job_id: UUID) -> Job | None:
        row = self._s.get(JobRow, job_id)
        return _job(row) if row else None

    def save(self, job: Job) -> Job:
        row = self._s.get(JobRow, job.id)
        if row is None:
            raise LookupError(f"job {job.id} не найден")
        for name in self._MUTABLE:
            setattr(row, name, getattr(job, name))
        self._s.flush()
        return job
