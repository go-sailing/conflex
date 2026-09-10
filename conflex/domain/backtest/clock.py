"""回测时钟：策略获取行情的唯一时间来源（SDD 8.1，防未来函数）。"""
from __future__ import annotations

import pandas as pd

from conflex.errors import LeakageError


class BacktestClock:
    def __init__(self, dates: pd.DatetimeIndex, strict: bool = True):
        self._dates = pd.DatetimeIndex(sorted(pd.to_datetime(dates).unique()))
        self._i = 0
        self.strict = strict

    @property
    def now(self) -> pd.Timestamp:
        return self._dates[self._i]

    @property
    def today(self) -> pd.Timestamp:
        return self.now

    def advance(self) -> bool:
        self._i += 1
        return self._i < len(self._dates)

    @property
    def finished(self) -> bool:
        return self._i >= len(self._dates)

    def __iter__(self):
        self._i = 0
        while self._i < len(self._dates):
            yield self._dates[self._i]
            self._i += 1

    def assert_visible(self, ts) -> None:
        if self.strict and pd.Timestamp(ts) > self.now:
            raise LeakageError(f"试图访问未来数据 {ts} > 当前回测日 {self.now}")
