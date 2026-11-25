"""Формат событий прогресса (TB-03 INT-3) и публикация в Redis pub/sub."""
from __future__ import annotations

import json
import logging

from ..domain.entities import Job, JobStatus

log = logging.getLogger(__name__)


def channel_name(job_id) -> str:
    return f"job:channel:{job_id}"


def job_event(job: Job) -> dict:
    """Сообщение WebSocket: type = progress | done | error."""
    if job.status == JobStatus.DONE:
        kind, message = "done", None
    elif job.status == JobStatus.FAILED:
        kind, message = "error", job.error_message
    elif job.status == JobStatus.CANCELLED:
        kind, message = "error", "Задача отменена"
    else:
        kind, message = "progress", None
    return {"type": kind, "job_id": str(job.id), "progress": job.progress,
            "status": job.status.value, "message": message}


class NullPublisher:
    def publish(self, job: Job) -> None:
        pass


class RedisPublisher:
    def __init__(self, redis_url: str):
        import redis

        self._client = redis.Redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)

    def publish(self, job: Job) -> None:
        try:
            self._client.publish(channel_name(job.id), json.dumps(job_event(job), ensure_ascii=False))
        except Exception:  # доставка прогресса — best effort, клиент догонит через polling
            log.warning("Не удалось опубликовать событие job %s", job.id, exc_info=True)
