"""令牌桶限频器（SDD 5.3）。"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, qps: float = 0.0, daily_quota: int = 0):
        self.qps = max(qps, 0.0)
        self.daily_quota = daily_quota
        self._tokens = self.qps
        self._last = time.monotonic()
        self._lock = threading.Lock()
        self.used_today = 0
        self.used_date = ""

    def quota_exhausted(self, today: str) -> bool:
        if self.daily_quota <= 0:
            return False
        if today != self.used_date:
            self.used_date = today
            self.used_today = 0
        return self.used_today >= self.daily_quota

    def acquire(self, today: str | None = None):
        """阻塞直到获得令牌；qps<=0 表示不限速。"""
        if self.qps <= 0:
            if today:
                self._bump_quota(today)
            return
        with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.qps, self._tokens + (now - self._last) * self.qps)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    if today:
                        self._bump_quota(today)
                    return
                time.sleep((1 - self._tokens) / self.qps)

    def _bump_quota(self, today: str):
        if today != self.used_date:
            self.used_date = today
            self.used_today = 0
        self.used_today += 1
