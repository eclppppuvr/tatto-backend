"""Реестр обработчиков задач по типу.

TB-03 добавит JobType.EXTRACT_SKETCH, TB-04 — GENERATE_DESIGN, TB-05 — TRY_ON.
Обработчик получает JobContext, при необходимости вызывает ctx.report(0..99) и возвращает output_ref.
Ошибки: TransientJobError — повторить с backoff, JobFailure — окончательный отказ.
"""
from __future__ import annotations

from ..ai.engine import AIEngine
from ..domain.entities import JobType
from ..services.runner import JobHandler
from ..storage import BlobStorage


def build_handlers(engine: AIEngine, storage: BlobStorage | None) -> dict[JobType, JobHandler]:
    return {}
