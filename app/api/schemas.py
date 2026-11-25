"""Pydantic-схемы запросов и ответов (контракты INT-1..INT-7 из TB-02)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from ..domain.entities import JobStatus, Role


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class RegisterResponse(BaseModel):
    id: UUID
    email: str
    role: Role
    access_token: str
    refresh_token: str


class UserShort(BaseModel):
    id: UUID
    email: str
    role: Role


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserShort


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str


class ProfileOut(BaseModel):
    display_name: str | None
    avatar_s3_key: str | None
    bio: str | None
    preferences: dict[str, Any]


class MeResponse(BaseModel):
    id: UUID
    email: str
    role: Role
    is_active: bool
    profile: ProfileOut | None
    created_at: datetime


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=500)
    preferences: dict[str, Any] | None = None


class SketchS3(BaseModel):
    thumbnail: str | None


class SketchItem(BaseModel):
    id: str
    title: str | None
    source: str
    s3: SketchS3
    created_at: datetime


class SketchPage(BaseModel):
    items: list[SketchItem]
    total: int
    page: int
    limit: int


class MessageResponse(BaseModel):
    message: str


class JobOut(BaseModel):
    id: UUID
    status: JobStatus
    progress: int
    output_ref: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
