"""Защита от перебора пароля: N неудачных входов с одного IP -> блокировка на M минут.
Хранилище в памяти процесса; при нескольких инстансах заменить на Redis."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from .domain.errors import TooManyAttempts


@dataclass
class _Entry:
    failures: int = 0
    first_failure_at: float = 0.0
    blocked_until: float = 0.0


class LoginRateLimiter:
    def __init__(self, max_failures: int = 5, block_seconds: float = 15 * 60,
                 clock: Callable[[], float] = time.monotonic):
        self.max_failures = max_failures
        self.block_seconds = block_seconds
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        with self._lock:
            entry = self._entries.get(key)
            if entry and entry.blocked_until > self._clock():
                raise TooManyAttempts()

    def fail(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            if len(self._entries) > 10_000:
                self._prune(now)
            entry = self._entries.setdefault(key, _Entry())
            # Окно подсчёта равно длительности блокировки.
            if entry.failures and now - entry.first_failure_at > self.block_seconds:
                entry.failures = 0
            if entry.failures == 0:
                entry.first_failure_at = now
            entry.failures += 1
            if entry.failures >= self.max_failures:
                entry.blocked_until = now + self.block_seconds
                entry.failures = 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def _prune(self, now: float) -> None:
        stale = [k for k, e in self._entries.items()
                 if e.blocked_until <= now and now - e.first_failure_at > self.block_seconds]
        for k in stale:
            del self._entries[k]
