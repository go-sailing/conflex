"""内置价量/技术因子（SDD 6.1，因子命名 类别_指标_窗口）。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from conflex.domain.factors.base import Factor, FactorRegistry
from conflex.domain.marketdata.panel import PanelData


@FactorRegistry.register(category="price", description="N 日动量（累计收益率）")
class Momentum(Factor):
    name = "price_mom_20"
    deps = ("close",)
    params = {"window": 20}

    def compute(self, panel: PanelData) -> pd.DataFrame:
        w = int(self.params["window"])
        close = panel.get("close")
        return close.pct_change(w)


@FactorRegistry.register(category="price", description="N 日反转（负动量）")
class Reversal(Factor):
    name = "price_rev_20"
    deps = ("close",)
    params = {"window": 20}

    def compute(self, panel: PanelData) -> pd.DataFrame:
        w = int(self.params["window"])
        return -panel.get("close").pct_change(w)


@FactorRegistry.register(category="risk", description="N 日收益率波动率（越低越好方向需自行取负）")
class Volatility(Factor):
    name = "risk_vol_60"
    deps = ("close",)
    params = {"window": 60}

    def compute(self, panel: PanelData) -> pd.DataFrame:
        w = int(self.params["window"])
        ret = panel.get("close").pct_change()
        return ret.rolling(w).std()


@FactorRegistry.register(category="liq", description="N 日日均成交额")
class AmountAvg(Factor):
    name = "liq_amtavg_20"
    deps = ("amount",)
    params = {"window": 20}

    def compute(self, panel: PanelData) -> pd.DataFrame:
        w = int(self.params["window"])
        return panel.get("amount").rolling(w).mean()


@FactorRegistry.register(category="liq", description="N 日换手率均值")
class TurnoverAvg(Factor):
    name = "liq_turnoveravg_20"
    deps = ("turnover",)
    params = {"window": 20}

    def compute(self, panel: PanelData) -> pd.DataFrame:
        w = int(self.params["window"])
        t = panel.get("turnover")
        return t.rolling(w).mean() if t is not None else pd.DataFrame()


@FactorRegistry.register(category="tech", description="RSI 相对强弱指标")
class RSI(Factor):
    name = "tech_rsi_14"
    deps = ("close",)
    params = {"window": 14}

    def compute(self, panel: PanelData) -> pd.DataFrame:
        w = int(self.params["window"])
        delta = panel.get("close").diff()
        up = delta.clip(lower=0).rolling(w).mean()
        down = (-delta.clip(upper=0)).rolling(w).mean()
        rs = up / down.replace(0, np.nan)
        return 100 - 100 / (1 + rs)


@FactorRegistry.register(category="price", description="N 日振幅均值（(high-low)/close）")
class Amplitude(Factor):
    name = "price_amp_20"
    deps = ("high", "low", "close")
    params = {"window": 20}

    def compute(self, panel: PanelData) -> pd.DataFrame:
        w = int(self.params["window"])
        amp = (panel.get("high") - panel.get("low")) / panel.get("close")
        return amp.rolling(w).mean()
