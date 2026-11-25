"""Заглушка AI-движка: возвращает белый PNG. Нужна для разработки и e2e-проверки очереди без моделей."""
from __future__ import annotations

import struct
import zlib
from typing import Any, Mapping

from .engine import ImageResult


def blank_png(width: int, height: int) -> bytes:
    """Валидный белый RGB PNG без внешних зависимостей."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    row = b"\x00" + b"\xff" * (width * 3)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height))
            + chunk(b"IEND", b""))


class StubEngine:
    name = "stub"
    SIZE = 256

    def _result(self) -> ImageResult:
        return ImageResult(blank_png(self.SIZE, self.SIZE), self.SIZE, self.SIZE, self.name)

    def extract_sketch(self, image: bytes, params: Mapping[str, Any] | None = None) -> ImageResult:
        return self._result()

    def generate_design(self, prompt: str, style: str) -> ImageResult:
        return self._result()

    def try_on(self, sketch_png: bytes, body_part: str, params: Mapping[str, Any] | None = None) -> ImageResult:
        return self._result()
