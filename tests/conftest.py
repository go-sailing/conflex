"""pytest 公共夹具：隔离数据目录 + 合成数据预填充。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from conflex.config import DataSourceCfg, Settings
from conflex.container import Container
from conflex.infra.datasources.synthetic import SyntheticDataSource

START = date(2022, 1, 4)
END = date(2024, 12, 31)
SEED_SYMBOLS = 10


@pytest.fixture(scope="session")
def seeded_container(tmp_path_factory) -> Container:
    data_dir = tmp_path_factory.mktemp("conflex_data")
    settings = Settings(
        data_dir=str(data_dir),
        datasources=[DataSourceCfg("synthetic", enabled=True, priority=99, qps=100)],
        max_retry=0,
    )
    c = Container(settings)
    src = SyntheticDataSource()
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
