"""多源代理：故障轮换、缓存命中不再联网、全源失败聚合异常。"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from conflex.config import DataSourceCfg, Settings
from conflex.errors import AllSourcesExhausted, SourceNetworkError
from conflex.infra.datasources.proxy import MarketDataProxy
from conflex.infra.db.database import Database
from conflex.infra.db.repositories.market import MarketRepository
from conflex.infra.db.repositories.system import SystemRepository


def _fake_bar(symbol="600519.SH"):
    dates = pd.bdate_range("2024-01-02", "2024-01-10")
    n = len(dates)
    close = 10 + np.arange(n)
    return pd.DataFrame({
        "symbol": symbol,
        "trade_date": pd.to_datetime(dates),
        "open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
        "volume": np.full(n, 1_000_000.0), "amount": close * 1_000_000,
        "turnover": 1.0, "pre_close": None, "suspended": False,
    })


class _FakeSource:
    def __init__(self, name, fail=False):
        self.name = name
        self.fail = fail
        self.calls = 0

    def fetch_daily_bars(self, symbol, start, end, adjust="none"):
        self.calls += 1
        if self.fail:
            raise SourceNetworkError(self.name, "模拟网络故障")
        return _fake_bar(symbol)

    def fetch_adjust_factors(self, symbol, start, end):
        return []

    def fetch_instruments(self):
        return []

    def fetch_calendar(self, start, end):
        return []

    def health_check(self):
        return not self.fail


def _build(tmp_path, sources):
    settings = Settings(data_dir=str(tmp_path))
    db = Database(settings.db_path)
    repo = MarketRepository(db, settings.market_dir)
    sysrepo = SystemRepository(db)
    cfg = DataSourceCfg("x", enabled=True, priority=1, qps=100)
    proxy = MarketDataProxy([(cfg, s) for s in sources], repo, sysrepo, max_retry=0)
    return proxy, repo, db


def test_failover_then_cache_hit(tmp_path):
    bad, good = _FakeSource("bad", fail=True), _FakeSource("good")
    proxy, repo, db = _build(tmp_path, [bad, good])

    df = proxy.get_daily("600519.SH", date(2024, 1, 2), date(2024, 1, 10))
    assert not df.empty
    assert bad.calls == 1 and good.calls == 1

    # 第二次：封闭数据全部本地命中，不再请求任何数据源
    df2 = proxy.get_daily("600519.SH", date(2024, 1, 2), date(2024, 1, 10))
    assert len(df2) == len(df)
    assert good.calls == 1

    cov = repo.coverage("600519.SH")
    assert cov[0] == date(2024, 1, 2) and cov[1] == date(2024, 1, 10)
    db.close()


def test_all_sources_exhausted(tmp_path):
    proxy, _, db = _build(tmp_path, [_FakeSource("a", True), _FakeSource("b", True)])
    with pytest.raises(AllSourcesExhausted) as exc:
        proxy.fetch_with_failover("600519.SH", date(2024, 1, 2), date(2024, 1, 10))
    assert any(src == "a" for src, _ in exc.value.attempts)
    assert any(src == "b" for src, _ in exc.value.attempts)
    db.close()
