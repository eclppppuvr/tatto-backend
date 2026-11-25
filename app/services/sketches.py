"""Заглушка истории эскизов. Эскизы живут в MongoDB и появляются в TB-03/TB-04;
до тех пор история пуста. Реализация на Mongo подставляется в app/api/deps.py."""
from __future__ import annotations

from uuid import UUID

from ..domain.entities import SketchSummary


class EmptySketchRepo:
    def list_by_user(self, user_id: UUID, page: int, limit: int) -> tuple[list[SketchSummary], int]:
        return [], 0
