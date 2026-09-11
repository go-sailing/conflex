"""数据源适配器基类：错误分类与字段标准化（SDD 5.1）。

适配器子类只需声明 COLUMN_MAP 并实现 _raw_daily()，返回原始 DataFrame。
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import date
from functools import wraps
from typing import Any

import pandas as pd

from conflex.domain.models import Instrument
from conflex.errors import (
    SourceAuthError, SourceBadRequest, SourceEmpty, SourceError,
    SourceNetworkError, SourceRateLimit,
)

STANDARD_COLUMNS = [
    "symbol", "trade_date", "open", "high", "low", "close",
    "volume", "amount", "turnover", "pre_close", "suspended",
]

AUTH_HINTS = ("token", "auth", "权限", "积分", "401", "403", "unauthorized")
LIMIT_HINTS = ("limit", "频率", "限频", "429", "too many", "每分钟", "每天")


def classify(source: str, exc: Exception) -> SourceError:
    """把底层 SDK/网络异常归类为 SourceError 子类。"""
    msg = str(exc).lower()
    if any(h in msg for h in AUTH_HINTS):
        return SourceAuthError(source, str(exc))
    if any(h in msg for h in LIMIT_HINTS):
        return SourceRateLimit(source, str(exc))
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return SourceNetworkError(source, str(exc))
    return SourceNetworkError(source, str(exc))


def guarded(fn):
    """统一计时/异常归类装饰器。"""

    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        start = time.monotonic()
        try:
            result = fn(self, *args, **kwargs)
            self.last_latency_ms = (time.monotonic() - start) * 1000
            return result
        except SourceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise classify(self.name, exc) from exc

    return wrapper


class BaseDataSource(ABC):
    name: str = "base"

    def __init__(self):
        self.last_latency_ms = 0.0

    # 子类实现：返回原始 DataFrame
    @abstractmethod
    def _raw_daily(self, symbol: str, start: date, end: date, adjust: str) -> pd.DataFrame: ...

    COLUMN_MAP: dict[str, str] = {}

    def _standardize(self, raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if raw is None or len(raw) == 0:
            raise SourceEmpty(self.name, f"{symbol} 返回空数据")
        df = raw.rename(columns=self.COLUMN_MAP).copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        if "symbol" not in df.columns:
            df["symbol"] = symbol
        for col in ("open", "high", "low", "close", "volume", "amount", "turnover", "pre_close"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "suspended" not in df.columns:
            df["suspended"] = False
        df["suspended"] = df["suspended"].fillna(False).astype(bool)
        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[STANDARD_COLUMNS].drop_duplicates("trade_date").sort_values("trade_date")
        # 构造 pre_close
        df["pre_close"] = df["pre_close"].fillna(df["close"].shift(1))
        return df.reset_index(drop=True)

    @guarded
    def fetch_daily_bars(self, symbol, start, end, adjust="none") -> pd.DataFrame:
        if start > end:
            raise SourceBadRequest(self.name, f"非法区间 {start}~{end}")
        raw = self._raw_daily(symbol, start, end, adjust)
        return self._standardize(raw, symbol)

    def fetch_adjust_factors(self, symbol, start, end):  # 默认无复权因子
        return []

    def fetch_instruments(self) -> list[Instrument]:
        return []

    def fetch_index_members(self, index_code: str) -> list[tuple[str, str]]:
        """指数成分股，返回 [(symbol, name), ...]（symbol 为 600000.SH 风格）。

        index_code 为交易所指数代码：000016 上证50 / 000300 沪深300 /
        000905 中证500 / 000852 中证1000。默认不支持。
        """
        return []

    def fetch_calendar(self, start: date, end: date) -> list[date]:
        return []

    def health_check(self) -> bool:
        try:
            self.fetch_calendar(date.today(), date.today())
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def is_auth_error(exc: Exception) -> bool:
        return isinstance(exc, SourceAuthError)
