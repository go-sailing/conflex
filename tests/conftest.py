"""pytest 公共夹具：隔离数据目录 + 内联测试数据生成。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from conflex.config import DataSourceCfg, Settings
from conflex.container import Container
from conflex.domain.models import Instrument
from conflex.infra.datasources.base import BaseDataSource, guarded

START = date(2022, 1, 4)
END = date(2024, 12, 31)
SEED_SYMBOLS = 10

_TEST_UNIVERSE = [
    ("600519.SH", "测试茅台"), ("000001.SZ", "测试平安"), ("600036.SH", "测试招行"),
    ("000858.SZ", "测试五粮液"), ("601318.SH", "测试平安保"), ("002594.SZ", "测试比亚迪"),
    ("600276.SH", "测试恒瑞"), ("601899.SH", "测试紫金"), ("000333.SZ", "测试美的"),
    ("600900.SH", "测试长电"), ("601088.SH", "测试神华"), ("000651.SZ", "测试格力"),
    ("600030.SH", "测试中信"), ("601012.SH", "测试隆基"), ("300750.SZ", "测试宁德"),
    ("688981.SH", "测试中芯"), ("002415.SZ", "测试海康"), ("600887.SH", "测试伊利"),
    ("601888.SH", "测试中免"), ("600031.SH", "测试三一"),
]


class _TestDataSource(BaseDataSource):
    """测试用数据源：确定性随机游走，无需网络。"""
    name = "test"

    def __init__(self, universe: list[tuple[str, str]] | None = None):
        super().__init__()
        self.universe = universe or _TEST_UNIVERSE

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

    @guarded
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


@pytest.fixture(scope="session")
def seeded_container(tmp_path_factory) -> Container:
    data_dir = tmp_path_factory.mktemp("conflex_data")
    settings = Settings(data_dir=str(data_dir), max_retry=0)
    src = _TestDataSource()
    adapters = [(DataSourceCfg("test", enabled=True, priority=99, qps=100), src)]
    c = Container(settings, adapters=adapters)
    c.market_repo.save_instruments(src.fetch_instruments()[:SEED_SYMBOLS])
    c.market_repo.save_calendar(src.fetch_calendar(START, END))
    symbols = [i.symbol for i in c.market_repo.load_instruments()]
    result = c.proxy.update_daily(symbols, START, END)
    assert result["failed"] == []
    yield c
    c.close()


@pytest.fixture()
def container(seeded_container) -> Container:
    """每个测试共享同一份只读种子数据，账户/回测结果互不影响。"""
    return seeded_container
