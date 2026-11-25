from __future__ import annotations

from uuid import UUID

from .celery_app import TASK_NAME
from .context import WorkerContext


def register_tasks(celery, ctx: WorkerContext) -> None:
    limit = ctx.settings.job_time_limit_seconds

    @celery.task(bind=True, name=TASK_NAME, soft_time_limit=limit, time_limit=limit + 15,
                 max_retries=ctx.settings.job_max_retries)
    def run_job(self, job_id: str) -> str:
        outcome = ctx.run(UUID(job_id))
        if outcome.status == "retry":
            raise self.retry(countdown=outcome.retry_in)
        return outcome.status
