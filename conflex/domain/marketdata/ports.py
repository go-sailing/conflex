"""领域端口：数据源适配器与本地仓储抽象（SDD 5.1）。infra 负责实现。"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd

from conflex.domain.models import AdjustFactor, Instrument


@runtime_checkable
class MarketDataSource(Protocol):
    name: str

    def fetch_daily_bars(
        self, symbol: str, start: date, end: date, adjust: str = "none"
    ) -> pd.DataFrame: ...

    def fetch_adjust_factors(
        self, symbol: str, start: date, end: date
    ) -> list[AdjustFactor]: ...

    def fetch_instruments(self) -> list[Instrument]: ...

    def fetch_calendar(self, start: date, end: date) -> list[date]: ...

    def health_check(self) -> bool: ...


@runtime_checkable
class BarRepository(Protocol):
    """本地行情仓储（Parquet + 元数据库）。"""

    def coverage(self, symbol: str) -> tuple[date, date] | None: ...

    def next_gap(self, symbol: str, start: date | None, end: date) -> tuple[date, date] | None: ...

    def read(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame: ...

    def read_many(
        self, symbols: list[str], start: date | None = None, end: date | None = None
    ) -> dict[str, pd.DataFrame]: ...

    def upsert(self, symbol: str, df: pd.DataFrame, is_final: bool = False) -> None: ...

    def load_instruments(self) -> list[Instrument]: ...

    def save_instruments(self, instruments: list[Instrument]) -> None: ...

    def load_calendar(self, start: date | None = None, end: date | None = None) -> list[date]: ...

    def save_calendar(self, dates: list[date]) -> None: ...
