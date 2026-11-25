"""Настройки сервиса. Всё чувствительное — только из переменных окружения."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_url: str
    jwt_secret: str
    access_ttl_minutes: int = 15      # TB-02 §5.1
    refresh_ttl_days: int = 7         # TB-02 §5.1
    bcrypt_rounds: int = 12           # TB-02 §5.1
    login_max_failures: int = 5       # TB-02 §5.2
    login_block_minutes: int = 15     # TB-02 §5.2
    cors_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.environ.get("JWT_SECRET", "")
        if len(secret) < 32:
            raise RuntimeError("JWT_SECRET должен быть задан и содержать не менее 32 символов")
        db_url = os.environ.get("DB_URL", "")
        if not db_url:
            raise RuntimeError("DB_URL не задан")
        origins = tuple(o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip())
        return cls(
            db_url=db_url,
            jwt_secret=secret,
            access_ttl_minutes=int(os.environ.get("ACCESS_TTL_MINUTES", 15)),
            refresh_ttl_days=int(os.environ.get("REFRESH_TTL_DAYS", 7)),
            bcrypt_rounds=int(os.environ.get("BCRYPT_ROUNDS", 12)),
            login_max_failures=int(os.environ.get("LOGIN_MAX_FAILURES", 5)),
            login_block_minutes=int(os.environ.get("LOGIN_BLOCK_MINUTES", 15)),
            cors_origins=origins,
        )
