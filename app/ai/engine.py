"""Интерфейс AI-движка (TB-03/04/05). Реализации подключаются по настройке AI_ENGINE."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

# TB-04: фиксированный набор стилей + custom
DESIGN_STYLES = ("minimalism", "old_school", "realism", "geometry", "japanese", "custom")


@dataclass(frozen=True)
class ImageResult:
    png: bytes
    width: int
    height: int
    model: str


class AIEngine(Protocol):
    name: str

    def extract_sketch(self, image: bytes, params: Mapping[str, Any] | None = None) -> ImageResult:
        """Фото тату на теле -> эскиз на белом фоне (TB-03)."""

    def generate_design(self, prompt: str, style: str) -> ImageResult:
        """Текст + стиль -> эскиз (TB-04)."""

    def try_on(self, sketch_png: bytes, body_part: str, params: Mapping[str, Any] | None = None) -> ImageResult:
        """Эскиз на манекен/часть тела (TB-05)."""


class EngineNotAvailable(Exception):
    """Запрошенная операция не поддерживается выбранным движком."""
