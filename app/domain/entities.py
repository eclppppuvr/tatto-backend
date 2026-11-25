"""Доменные сущности, не зависящие от ORM и веб-фреймворка."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class Role(str, Enum):
    CLIENT = "client"
    MASTER = "master"
    ADMIN = "admin"


@dataclass
class User:
    id: UUID
    email: str
    hashed_password: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class Profile:
    user_id: UUID
    display_name: str | None = None
    avatar_s3_key: str | None = None
    bio: str | None = None
    preferences: dict = field(default_factory=dict)


@dataclass
class RefreshToken:
    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked: bool
    created_at: datetime


@dataclass
class SketchSummary:
    id: str
    title: str | None
    source: str            # extract | generation
    thumbnail: str | None  # s3-ключ миниатюры
    created_at: datetime
