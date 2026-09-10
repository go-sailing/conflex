"""回测应用服务：组装数据→因子→引擎→落库（SDD 8.5）。"""
from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd

import conflex
from conflex.application.selection_service import SelectionService
from conflex.domain.backtest.engine import BacktestConfig, BacktestEngine
from conflex.domain.backtest.strategy import CrossSectionalStrategy
from conflex.domain.portfolio.cost import CostPolicy
from conflex.domain.portfolio.matcher import broker_factory


class BacktestService:
    def __init__(self, market_repo, trading_repo, factor_service, job_manager=None):
        self.mr = market_repo
        self.tr = trading_repo
        self.factor_service = factor_service
        self.selection = SelectionService(factor_service, market_repo)
        self.jobs = job_manager

    def _resolve_symbols(self, params: dict) -> list[str]:
        if params.get("symbols"):
            return params["symbols"]
        return self.mr.symbols_on_disk() or self.mr.listed_symbols()

    def run_sync(self, params: dict, job_ctx=None) -> dict:
        start, end = params["start"], params["end"]
        symbols = self._resolve_symbols(params)
        if job_ctx:
            job_ctx.report_progress(0.05, f"加载 {len(symbols)} 只股票行情")
        adjust = params.get("adjust", "qfq")
        frames = self.mr.read_many(symbols, pd.Timestamp(start).date(),
                                   pd.Timestamp(end).date(), adjust=adjust)
        bars = {s: df.set_index(pd.to_datetime(df["trade_date"]))
                for s, df in frames.items() if not df.empty}
        if not bars:
            raise ValueError("回测区间内无行情数据，请先更新数据")

        panel = self.factor_service.load_panel(list(bars), start, end, adjust)
        specs = params["factors"]
        if job_ctx:
            job_ctx.report_progress(0.35, f"计算 {len(specs)} 个因子")
        scores = self.selection.score_frame(
            specs, panel, weighting=params.get("weighting", "equal"))

        benchmark = None
        bm = params.get("benchmark")
        if bm and bm in bars:
            benchmark = bars[bm]["close"]

        if job_ctx:
            job_ctx.report_progress(0.55, "回测主循环")
        cost = CostPolicy(
            commission_rate=params.get("commission_rate", 0.00025),
            commission_min=params.get("commission_min", 5.0),
            stamp_tax_rate=params.get("stamp_tax_rate", 0.001),
            slippage_bps=params.get("slippage_bps", 5.0),
        )
        broker = broker_factory(params.get("broker", "next_open"), cost)
        strategy = CrossSectionalStrategy(
            top_n=int(params.get("top_n", 20)),
            rebalance=params.get("rebalance", "M"),
            weighting=params.get("position_weighting", "equal"),
        )
        cfg = BacktestConfig(start=start, end=end,
                             initial_cash=float(params.get("initial_cash", 1_000_000)))
        engine = BacktestEngine(bars=bars, scores=scores, strategy=strategy,
                                broker=broker, config=cfg, benchmark=benchmark)
        result = engine.run()
        if job_ctx:
            job_ctx.report_progress(0.9, "持久化结果")

        run_params = {**params, "data_version": datetime.now().strftime("%Y%m%d"),
                      "code_version": conflex.__version__}
        run_id = self.tr.create_backtest_run(
            name=params.get("name", "backtest"), params=run_params,
            start=str(start), end=str(end), benchmark=bm or "")
        equity = result.equity
        peak = equity.cummax()
        drawdown = 1 - equity / peak
        self.tr.save_equity(run_id, equity, result.benchmark, drawdown)
        self.tr.save_backtest_trades(run_id, result.trades)
        self.tr.finish_backtest_run(run_id, "succeeded", result.metrics)
        return {"run_id": run_id, "metrics": result.metrics,
                "trades": int(len(result.trades))}

    def submit(self, params: dict, created_by: int | None = None) -> int:
        return self.jobs.submit("backtest", params,
                                lambda ctx: self.run_sync(params, ctx), created_by)

    def list_runs(self):
        return self.tr.list_backtests()

    def get_run(self, run_id: int):
        return self.tr.get_backtest(run_id)
