"""策略抽象与上下文（SDD 8.2）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 避免运行时循环依赖
    from conflex.domain.backtest.engine import Context


class Strategy(ABC):
    name: str = "strategy"

    def on_start(self, ctx: "Context") -> None: ...

    @abstractmethod
    def on_bar(self, ctx: "Context", today) -> None: ...

    def on_end(self, ctx: "Context") -> None: ...


class CrossSectionalStrategy(Strategy):
    """多因子截面选股：调仓日选综合得分 Top N，等权/得分加权，目标持仓调仓。"""

    name = "cross_sectional"

    def __init__(
        self,
        top_n: int = 20,
        rebalance: str = "M",   # D / W / M
        weighting: str = "equal",
    ):
        self.top_n = top_n
        self.rebalance = rebalance.upper()
        self.weighting = weighting

    def on_bar(self, ctx: "Context", today) -> None:
        if not ctx.is_rebalance_day(self.rebalance):
            return
        row = ctx.score_row(today).dropna()
        # 剔除当日停牌
        tradable = [s for s in row.index if not ctx.is_suspended(s, today)]
        row = row.loc[tradable].sort_values(ascending=False).head(self.top_n)
        if row.empty:
            return
        if self.weighting == "score" and (row > 0).all():
            weights = (row / row.sum()).to_dict()
        else:
            w = 1.0 / len(row)
            weights = {s: w for s in row.index}
        ctx.rebalance(weights, signal_date=today)
