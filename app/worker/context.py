from __future__ import annotations

from typing import Mapping
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..domain.entities import JobType
from ..domain.ports import EventPublisher
from ..db.repos import SqlJobRepo
from ..services.runner import JobHandler, JobRunner, RunOutcome


class WorkerContext:
    """Всё, что воркеру нужно для обработки одной задачи; сессия БД — на каждый запуск."""

    def __init__(self, settings: Settings, session_factory: sessionmaker[Session],
                 publisher: EventPublisher, handlers: Mapping[JobType, JobHandler]):
        self.settings = settings
        self._session_factory = session_factory
        self._publisher = publisher
        self._handlers = handlers

    def run(self, job_id: UUID) -> RunOutcome:
        from celery.exceptions import SoftTimeLimitExceeded

        with self._session_factory() as session:
            runner = JobRunner(
                SqlJobRepo(session), self._publisher, self._handlers, commit=session.commit,
                max_retries=self.settings.job_max_retries, timeout_exceptions=(SoftTimeLimitExceeded,),
            )
            return runner.run(job_id)
