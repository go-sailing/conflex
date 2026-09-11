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
                groups: int = 10, params: dict | None = None,
                clip_start: date | str | None = None,
                universe: str | None = None,
                requested_count: int | None = None) -> dict:
        factor = self.compute(name, panel, params)
        close = panel.get("close")
        fwd = forward_returns(close, horizon)

        # 面板可能为滚动窗口预留了 warmup（start 之前的行情），
        # IC/分层统计只截取用户请求的分析区间
        if clip_start is not None:
            ts = pd.Timestamp(clip_start)
            factor = factor.loc[factor.index >= ts]
            fwd = fwd.loc[fwd.index >= ts]

        # ---- 前置校验：数据是否足够 ----
        n_rows = factor.shape[0] if factor.shape[0] else 0
        factor_nan = factor.isna().sum().sum() / max(factor.shape[0] * factor.shape[1], 1)
        fwd_nan = fwd.isna().sum().sum() / max(fwd.shape[0] * fwd.shape[1], 1)
        warnings: list[str] = []
        min_window = 20  # price_rev_20 等常用因子的最小窗口
        if n_rows < min_window:
            warnings.append(
                f"行情面板仅 {n_rows} 个交易日，"
                f"{name} 因子需要至少 {min_window} 天窗口才能计算。"
                f"请扩大分析的开始日期范围（行情缺失部分会在分析前自动增量拉取）。"
            )
        if factor_nan >= 0.95:
            warnings.append(
                f"{name} 因子计算结果 {factor_nan:.0%} 为 NaN，"
                f"可能是行情数据不足或因子参数不匹配。"
            )
        if fwd_nan >= 0.80:
            warnings.append(
                f"未来收益（预测{horizon}日）{fwd_nan:.0%} 为 NaN，"
                f"面板尾部交易日不足 {horizon} 天。"
            )

        ic = ic_series(factor, fwd)
        layered = layered_returns(factor, fwd, groups)
        result = {
            "factor": name,
            "universe": universe or "all",
            "requested_count": requested_count,
            "panel_count": int(close.shape[1]),
            "horizon": horizon,
            "groups": groups,
            "summary": ic_summary(ic),
            "ic_series": [{"date": d.date().isoformat(), "ic": (None if pd.isna(v) else float(v))}
                          for d, v in ic.items()],
            "layered_mean": (None if layered.empty else
                             {f"G{i+1}": float(v) for i, v in enumerate(layered.mean())}),
        }
        if warnings:
            result["warnings"] = warnings
        return result
