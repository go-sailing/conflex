"""因子应用服务：面板加载、因子计算、有效性分析（SDD 6.2、6.5）。"""
from __future__ import annotations

from datetime import date

import pandas as pd

from conflex.domain.factors.analysis import (
    factor_correlation, forward_returns, ic_series, ic_summary, layered_returns,
)
from conflex.domain.factors.base import FactorRegistry, factor_cache_key
from conflex.domain.factors.preprocess import run_pipeline
from conflex.domain.marketdata.panel import FIELD_NAMES, PanelData

_FIELDS = FIELD_NAMES


class FactorService:
    def __init__(self, repo):
        self.repo = repo

    def list_factors(self) -> list[dict]:
        FactorRegistry.ensure_builtins()
        return [
            {"name": m.name, "category": m.category, "description": m.description,
             "deps": list(m.deps), "params": m.params}
            for m in FactorRegistry.list()
        ]

    def load_panel(self, symbols: list[str], start: date | str | None,
                   end: date | str | None, adjust: str = "none",
                   fields=_FIELDS) -> PanelData:
        """从仓储读取多只股票，组装 日期×股票 面板（停牌日 NaN 对齐）。"""
        frames: dict[str, dict[str, pd.DataFrame]] = {f: {} for f in fields}
        for sym in symbols:
            df = self.repo.read(sym, start, end, adjust)
            if df.empty:
                continue
            df = df.set_index(pd.to_datetime(df["trade_date"]))
            for f in fields:
                if f in df.columns:
                    frames[f][sym] = df[f]
        panels = {}
        for f, by_sym in frames.items():
            if by_sym:
                panels[f] = pd.DataFrame(by_sym).sort_index()
        if "close" not in panels:
            raise ValueError("本地无可用行情，请先更新数据")
        return PanelData(panels)

    def compute(self, name: str, panel: PanelData, params: dict | None = None,
                preprocess: bool = True) -> pd.DataFrame:
        factor = FactorRegistry.create(name, **(params or {}))
        raw = factor.compute(panel)
        return run_pipeline(raw) if preprocess else raw

    def compute_many(self, specs: list[dict], panel: PanelData) -> dict[str, pd.DataFrame]:
        out = {}
        for spec in specs:
            out[spec["name"]] = self.compute(
                spec["name"], panel, spec.get("params"),
                preprocess=spec.get("preprocess", True))
        return out

    def analyze(self, name: str, panel: PanelData, horizon: int = 5,
                groups: int = 10, params: dict | None = None) -> dict:
        factor = self.compute(name, panel, params)
        close = panel.get("close")
        fwd = forward_returns(close, horizon)
        ic = ic_series(factor, fwd)
        layered = layered_returns(factor, fwd, groups)
        return {
            "factor": name,
            "horizon": horizon,
            "groups": groups,
            "summary": ic_summary(ic),
            "ic_series": [{"date": d.date().isoformat(), "ic": (None if pd.isna(v) else float(v))}
                          for d, v in ic.items()],
            "layered_mean": (None if layered.empty else
                             {f"G{i+1}": float(v) for i, v in enumerate(layered.mean())}),
        }
