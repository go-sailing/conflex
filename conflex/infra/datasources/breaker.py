"""熔断器 CLOSED→OPEN→HALF_OPEN（SDD 5.3）。"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock


class CircuitBreaker:
    def __init__(self, fail_threshold: int = 5, cooldown_seconds: int = 300,
                 window_seconds: int = 600):
        self.fail_threshold = fail_threshold
        self.cooldown = cooldown_seconds
        self.window = window_seconds
        self._fails: deque[float] = deque()
        self._opened_at: float | None = None
        self.state = "closed"
        self._lock = Lock()

    def allow(self) -> bool:
        with self._lock:
            if self.state != "open":
                return True
            if time.monotonic() - (self._opened_at or 0) >= self.cooldown:
                self.state = "half_open"
                return True
            return False

    def record_success(self):
        with self._lock:
            self._fails.clear()
            self._opened_at = None
            self.state = "closed"

    def record_failure(self) -> str:
        with self._lock:
            now = time.monotonic()
            self._fails.append(now)
            while self._fails and now - self._fails[0] > self.window:
                self._fails.popleft()
            if self.state == "half_open" or len(self._fails) >= self.fail_threshold:
                self.state = "open"
                self._opened_at = now
            return self.state
