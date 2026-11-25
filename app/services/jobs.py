"""Создание и чтение задач (API-сторона)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable
from uuid import UUID, uuid4

from ..domain.entities import Job, JobStatus, JobType
from ..domain.errors import JobForbidden, JobNotFound
from ..domain.ports import JobDispatcher, JobRepo
from .auth import utcnow

log = logging.getLogger(__name__)

# TB-03 §5.1: cpu — extract и generation, gpu — try-on.
QUEUE_BY_TYPE = {
    JobType.EXTRACT_SKETCH: "cpu",
    JobType.GENERATE_DESIGN: "cpu",
    JobType.TRY_ON: "gpu",
}


class NullDispatcher:
    """Используется, когда Redis/Celery не настроены: job остаётся pending."""

    def dispatch(self, job: Job) -> None:
        log.warning("Брокер не настроен: job %s остаётся в pending", job.id)


class JobService:
    def __init__(self, jobs: JobRepo, dispatcher: JobDispatcher,
                 commit: Callable[[], None] = lambda: None,
                 clock: Callable[[], datetime] = utcnow):
        self._jobs = jobs
        self._dispatcher = dispatcher
        self._commit = commit
        self._clock = clock

    def create(self, user_id: UUID, job_type: JobType, input_ref: str) -> Job:
        now = self._clock()
        return self._jobs.add(Job(
            id=uuid4(), user_id=user_id, type=job_type, status=JobStatus.PENDING, progress=0,
            input_ref=input_ref, output_ref=None, error_code=None, error_message=None, retry_count=0,
            created_at=now, updated_at=now,
        ))

    def submit(self, user_id: UUID, job_type: JobType, input_ref: str) -> Job:
        """Создаёт job, фиксирует транзакцию и только потом ставит в очередь.
        Иначе воркер может взять job раньше, чем она станет видна в БД.
        Недоступность брокера не ломает приём: job остаётся pending (TB-03 §5.2)."""
        job = self.create(user_id, job_type, input_ref)
        self._commit()
        try:
            self._dispatcher.dispatch(job)
        except Exception:
            log.exception("Не удалось поставить job %s в очередь, остаётся pending", job.id)
        return job

    def get_for_user(self, user_id: UUID, job_id: UUID) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFound()
        if job.user_id != user_id:
            raise JobForbidden()
        return job
