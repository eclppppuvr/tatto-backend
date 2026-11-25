from __future__ import annotations

from ..config import Settings

TASK_NAME = "app.worker.run_job"


def make_celery(settings: Settings):
    from celery import Celery

    broker = settings.broker_url
    if not broker:
        raise RuntimeError("Не задан REDIS_URL или CELERY_BROKER_URL")
    app = Celery("tattoo", broker=broker)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        task_default_queue="cpu",
        task_acks_late=True,                 # задача подтверждается после выполнения
        task_reject_on_worker_lost=True,     # при падении воркера сообщение вернётся в очередь
        worker_prefetch_multiplier=1,        # тяжёлые задачи: не набирать лишнего в запас
        broker_connection_timeout=2,         # API не должен зависать, если брокер недоступен
        broker_connection_retry_on_startup=True,
    )
    return app
