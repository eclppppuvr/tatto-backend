from __future__ import annotations

from .engine import AIEngine
from .stub import StubEngine


def get_engine(name: str) -> AIEngine:
    """TB-03 добавит 'opencv', TB-04 — 'yandex', TB-05 — 'sd'."""
    if name == "stub":
        return StubEngine()
    raise ValueError(f"Неизвестный AI_ENGINE: {name!r}")
