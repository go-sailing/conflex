"""合成数据源：确定性随机游走，供离线演示、测试与兜底（非真实行情）。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from conflex.domain.models import Instrument
from conflex.infra.datasources.base import BaseDataSource

# 固定演示股票池
_DEMO_UNIVERSE = [
    ("600519.SH", "演示茅台"), ("000001.SZ", "演示平安"), ("600036.SH", "演示招行"),
    ("000858.SZ", "演示五粮液"), ("601318.SH", "演示平安保"), ("002594.SZ", "演示比亚迪"),
    ("600276.SH", "演示恒瑞"), ("601899.SH", "演示紫金"), ("000333.SZ", "演示美的"),
    ("600900.SH", "演示长电"), ("601088.SH", "演示神华"), ("000651.SZ", "演示格力"),
    ("600030.SH", "演示中信"), ("601012.SH", "演示隆基"), ("300750.SZ", "演示宁德"),
    ("688981.SH", "演示中芯"), ("002415.SZ", "演示海康"), ("600887.SH", "演示伊利"),
    ("601888.SH", "演示中免"), ("600031.SH", "演示三一"),
]


class SyntheticDataSource(BaseDataSource):
    name = "synthetic"

    def __init__(self, universe: list[tuple[str, str]] | None = None):
        super().__init__()
        self.universe = universe or _DEMO_UNIVERSE

    def fetch_instruments(self) -> list[Instrument]:
        out = []
        for symbol, name in self.universe:
            code = symbol.split(".")[0]
            board = ("star" if code.startswith(("688", "689"))
                     else "chinext" if code.startswith(("300", "301")) else "main")
            out.append(Instrument(symbol=symbol, name=name, exchange=symbol[-2:],
                                  board=board, list_date=date(2018, 1, 1)))
        return out

    def fetch_calendar(self, start: date, end: date) -> list[date]:
        days = []
        cur = start
        while cur <= end:
            if cur.weekday() < 5:
                days.append(cur)
            cur += timedelta(days=1)
        return days

    def _seed(self, symbol: str) -> int:
        return int(symbol.split(".")[0]) % 100000

    def _raw_daily(self, symbol: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        cal = self.fetch_calendar(start, end)
        n = len(cal)
        seed = self._seed(symbol) + start.year * 12 + start.month
        rng = np.random.default_rng(seed)
        drift, vol = 0.0004, 0.016
        rets = rng.normal(drift, vol, n)
        base = 10 + (self._seed(symbol) % 90)
        close = base * np.cumprod(1 + rets)
        open_ = close * (1 + rng.normal(0, 0.004, n))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
        volume = rng.integers(2_000_000, 50_000_000, n).astype(float)
        amount = volume * close
        df = pd.DataFrame({
            "trade_date": pd.to_datetime(cal),
            "open": open_.round(2), "high": high.round(2),
            "low": low.round(2), "close": close.round(2),
            "volume": volume, "amount": amount.round(2),
            "turnover": rng.uniform(0.5, 4.0, n).round(3),
        })
        df["symbol"] = symbol
        return df
