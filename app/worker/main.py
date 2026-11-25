"""Точка входа воркера:
    celery -A app.worker.main:celery worker -Q cpu -l info
    celery -A app.worker.main:celery worker -Q gpu -l info   (try-on, TB-05)
"""
from __future__ import annotations

from ..ai.registry import get_engine
from ..config import Settings
from ..db.session import make_engine, make_session_factory
from ..services.events import NullPublisher, RedisPublisher
from ..storage import S3Storage
from .celery_app import make_celery
from .context import WorkerContext
from .handlers import build_handlers
from .tasks import register_tasks

settings = Settings.from_env()
celery = make_celery(settings)

storage = None
if settings.s3_endpoint_url:
    storage = S3Storage(settings.s3_endpoint_url, settings.s3_access_key, settings.s3_secret_key,
                        settings.s3_bucket, settings.s3_region)

publisher = RedisPublisher(settings.redis_url) if settings.redis_url else NullPublisher()
register_tasks(celery, WorkerContext(
    settings, make_session_factory(make_engine(settings.db_url)), publisher,
    build_handlers(get_engine(settings.ai_engine), storage),
))
