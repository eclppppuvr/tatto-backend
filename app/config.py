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
    # --- инфраструктура фоновых задач (TB-03/04/05); None = компонент не настроен ---
    redis_url: str | None = None           # pub/sub для WebSocket и (по умолчанию) брокер Celery
    celery_broker_url: str | None = None   # если не задан, используется redis_url
    s3_endpoint_url: str | None = None     # MinIO/S3
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "tattoo"
    s3_region: str = "us-east-1"
    ai_engine: str = "stub"
    job_time_limit_seconds: int = 120      # hard-limit AI-обработки (БТ)
    job_max_retries: int = 3               # TB-03 §5.1

    @property
    def broker_url(self) -> str | None:
        return self.celery_broker_url or self.redis_url

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
            redis_url=os.environ.get("REDIS_URL") or None,
            celery_broker_url=os.environ.get("CELERY_BROKER_URL") or None,
            s3_endpoint_url=os.environ.get("S3_URL") or None,
            s3_access_key=os.environ.get("S3_ACCESS_KEY") or None,
            s3_secret_key=os.environ.get("S3_SECRET_KEY") or None,
            s3_bucket=os.environ.get("S3_BUCKET", "tattoo"),
            s3_region=os.environ.get("S3_REGION", "us-east-1"),
            ai_engine=os.environ.get("AI_ENGINE", "stub"),
            job_time_limit_seconds=int(os.environ.get("JOB_TIME_LIMIT_SECONDS", 120)),
            job_max_retries=int(os.environ.get("JOB_MAX_RETRIES", 3)),
        )
