from __future__ import annotations

from ..config import Settings
from ..domain.entities import Job
from ..services.jobs import QUEUE_BY_TYPE, NullDispatcher
from .celery_app import TASK_NAME, make_celery


class CeleryDispatcher:
    def __init__(self, celery):
        self._celery = celery

    def dispatch(self, job: Job) -> None:
        self._celery.send_task(
            TASK_NAME, args=[str(job.id)], queue=QUEUE_BY_TYPE[job.type],
            retry=True, retry_policy={"max_retries": 1, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5},
        )


def build_dispatcher(settings: Settings):
    if settings.broker_url:
        return CeleryDispatcher(make_celery(settings))
    return NullDispatcher()
