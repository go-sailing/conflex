"""依赖注入容器（SDD 2.2 / 3.2）：组装各层实现。"""
from __future__ import annotations

from conflex.config import DataSourceCfg, Settings, load_settings
from conflex.application.backtest_service import BacktestService
from conflex.application.factor_service import FactorService
from conflex.application.jobs import JobManager
from conflex.application.market_service import MarketService
from conflex.application.paper_service import PaperService
from conflex.application.selection_service import SelectionService
from conflex.infra.datasources.akshare_source import AkshareDataSource
from conflex.infra.datasources.baostock_source import BaostockDataSource
from conflex.infra.datasources.efinance_source import EfinanceDataSource
from conflex.infra.datasources.proxy import MarketDataProxy
from conflex.infra.datasources.sina_source import SinaDataSource
from conflex.infra.datasources.tencent_source import TencentDataSource
from conflex.infra.datasources.tushare_source import TushareDataSource
from conflex.infra.db.database import Database
from conflex.infra.db.repositories.market import MarketRepository
from conflex.infra.db.repositories.system import SystemRepository
from conflex.infra.db.repositories.trading import TradingRepository


class Container:
    def __init__(self, settings: Settings | None = None, config_file: str | None = None,
                 adapters: list[tuple[DataSourceCfg, object]] | None = None):
        self.settings = settings or load_settings(config_file)
        self.db = Database(self.settings.db_path)
        self.market_repo = MarketRepository(self.db, self.settings.market_dir)
        self.trading_repo = TradingRepository(self.db)
        self.system_repo = SystemRepository(self.db)

        adapters = adapters if adapters is not None else self._build_sources()
        self._register_source_stats(adapters)
        self.proxy = MarketDataProxy(
            adapters, self.market_repo, self.system_repo,
            max_retry=self.settings.max_retry,
            fail_threshold=self.settings.breaker_fail_threshold,
            cooldown_seconds=self.settings.breaker_cooldown_seconds,
        )
        self.jobs = JobManager(self.system_repo)
        self.factor_service = FactorService(self.market_repo)
        self.selection_service = SelectionService(self.factor_service, self.market_repo)
        self.market_service = MarketService(self.proxy, self.market_repo, self.jobs)
        self.paper_service = PaperService(self.trading_repo, self.market_repo, self.settings)
        self.backtest_service = BacktestService(
            self.market_repo, self.trading_repo, self.factor_service, self.jobs)

    def _build_sources(self) -> list[tuple[DataSourceCfg, object]]:
        out: list[tuple[DataSourceCfg, object]] = []
        for cfg in sorted(self.settings.datasources, key=lambda c: c.priority):
            if not cfg.enabled:
                continue
            try:
                if cfg.name == "tushare":
                    token = cfg.token()
                    if not token:
                        continue
                    out.append((cfg, TushareDataSource(token=token)))
                elif cfg.name == "akshare":
                    out.append((cfg, AkshareDataSource()))
                elif cfg.name == "baostock":
                    out.append((cfg, BaostockDataSource()))
                elif cfg.name == "efinance":
                    out.append((cfg, EfinanceDataSource()))
                elif cfg.name == "tencent":
                    out.append((cfg, TencentDataSource()))
                elif cfg.name == "sina":
                    out.append((cfg, SinaDataSource()))
            except Exception:  # noqa: BLE001 适配器不可用则跳过
                continue
        return out

    def _register_source_stats(self, adapters):
        for cfg, adapter in adapters:
            self.market_repo.upsert_source_stat(
                cfg.name, cfg.enabled, cfg.priority, cfg.qps, cfg.daily_quota)

    def close(self):
        self.jobs.executor.shutdown(wait=False)
        self.db.close()
