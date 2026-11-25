"""Исполнитель задач: переходы статусов, прогресс, retry с backoff, таймаут.
Не зависит от Celery/ORM: хранилище, публикация и команда commit передаются снаружи."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping
from uuid import UUID

from ..domain.entities import TERMINAL_STATUSES, Job, JobStatus, JobType
from ..domain.errors import JobFailure, JobTimeout, TransientJobError
from ..domain.ports import EventPublisher, JobRepo
from .auth import utcnow

log = logging.getLogger(__name__)

BACKOFF_SECONDS = (10, 30, 90)  # TB-03 §5.1


class JobContext:
    """Что видит обработчик задачи."""

    def __init__(self, job: Job, report: Callable[[int], None]):
        self.job_id = job.id
        self.user_id = job.user_id
        self.type = job.type
        self.input_ref = job.input_ref
        self._report = report

    def report(self, progress: int) -> None:
        self._report(progress)


JobHandler = Callable[[JobContext], str]  # возвращает output_ref


@dataclass(frozen=True)
class RunOutcome:
    status: str                      # done | failed | retry | skipped
    retry_in: int | None = None      # секунды, только для retry


class JobRunner:
    def __init__(self, jobs: JobRepo, publisher: EventPublisher, handlers: Mapping[JobType, JobHandler],
                 commit: Callable[[], None] = lambda: None, clock: Callable[[], datetime] = utcnow,
                 max_retries: int = 3, backoff: tuple[int, ...] = BACKOFF_SECONDS,
                 timeout_exceptions: tuple[type[BaseException], ...] = ()):
        self._jobs = jobs
        self._publisher = publisher
        self._handlers = handlers
        self._commit = commit
        self._clock = clock
        self._max_retries = max_retries
        self._backoff = backoff
        self._timeout_exceptions = timeout_exceptions

    def run(self, job_id: UUID) -> RunOutcome:
        job = self._jobs.get(job_id)
        if job is None:
            log.warning("job %s не найден, пропускаем", job_id)
            return RunOutcome("skipped")
        if job.status in TERMINAL_STATUSES:  # повторная доставка сообщения из очереди
            return RunOutcome("skipped")

        handler = self._handlers.get(job.type)
        if handler is None:
            self._fail(job, "not_implemented", f"Обработчик для {job.type.value} не подключён")
            return RunOutcome("failed")

        if job.status == JobStatus.RUNNING:
            # Сообщение пришло повторно, хотя job уже «выполнялась»: воркер упал или был убит по hard-limit.
            # Считаем это неудачной попыткой, чтобы упавшая задача не крутилась бесконечно.
            if job.retry_count >= self._max_retries:
                self._fail(job, "worker_lost", "Обработка прервана: воркер остановился")
                return RunOutcome("failed")
            job.retry_count += 1

        now = self._clock()
        job.status = JobStatus.RUNNING
        job.started_at = job.started_at or now
        job.error_code = job.error_message = None
        self._persist(job)

        try:
            output_ref = handler(JobContext(job, lambda p: self._report(job, p)))
        except TransientJobError as exc:
            return self._retry_or_fail(job, exc)
        except JobFailure as exc:
            self._fail(job, exc.code, exc.message)
            return RunOutcome("failed")
        except BaseException as exc:
            if self._timeout_exceptions and isinstance(exc, self._timeout_exceptions):
                self._fail(job, JobTimeout.code, JobTimeout.message)
                return RunOutcome("failed")
            if not isinstance(exc, Exception):
                raise
            log.exception("Необработанная ошибка в job %s", job.id)
            self._fail(job, "internal_error", "Внутренняя ошибка обработки")  # детали наружу не отдаём
            return RunOutcome("failed")

        job.status = JobStatus.DONE
        job.progress = 100
        job.output_ref = output_ref
        job.finished_at = self._clock()
        self._persist(job)
        return RunOutcome("done")

    # --- внутреннее ---
    def _report(self, job: Job, progress: int) -> None:
        progress = max(0, min(int(progress), 99))  # 100 ставится только при done
        if progress > job.progress:                # прогресс не откатывается назад
            job.progress = progress
            self._persist(job)

    def _retry_or_fail(self, job: Job, exc: TransientJobError) -> RunOutcome:
        if job.retry_count >= self._max_retries:
            self._fail(job, exc.code, exc.message)
            return RunOutcome("failed")
        delay = self._backoff[min(job.retry_count, len(self._backoff) - 1)]
        job.retry_count += 1
        job.status = JobStatus.PENDING
        self._persist(job)
        return RunOutcome("retry", retry_in=delay)

    def _fail(self, job: Job, code: str, message: str) -> None:
        job.status = JobStatus.FAILED
        job.error_code, job.error_message = code, message
        job.finished_at = self._clock()
        self._persist(job)

    def _persist(self, job: Job) -> None:
        job.updated_at = self._clock()
        self._jobs.save(job)
        self._commit()
        self._publisher.publish(job)  # после коммита: подписчик, перечитав БД, увидит то же состояние
