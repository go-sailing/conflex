"""撮合器：回测与模拟交易共用同一套成交规则（SDD 7.3）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import pandas as pd

from conflex.domain.models import DailyBar, Fill, Side
from conflex.domain.portfolio.cost import CostPolicy
from conflex.domain.portfolio.order import Order


def limit_prices(pre_close: float | None, board: str = "main") -> tuple[float, float]:
    """涨跌停价（容差 0.5%）。"""
    if not pre_close:
        return float("inf"), 0.0
    pct = 0.20 if board in ("star", "chinext", "bjt") else 0.10
    return pre_close * (1 + pct), pre_close * (1 - pct)


@dataclass
class MatchConfig:
    board_of: dict[str, str] | None = None
    volume_participation: float = 0.0   # >0 时限制单笔不超过 bar 成交量的比例

    def board(self, symbol: str) -> str:
        if self.board_of and symbol in self.board_of:
            return self.board_of[symbol]
        code = symbol.split(".")[0]
        if code.startswith(("688", "689")):
            return "star"
        if code.startswith(("300", "301")):
            return "chinext"
        if symbol.endswith(".BJ"):
            return "bjt"
        return "main"


class Broker(ABC):
    def __init__(self, cost_policy: CostPolicy, config: MatchConfig | None = None):
        self.cost = cost_policy
        self.cfg = config or MatchConfig()

    @abstractmethod
    def match(self, order: Order, bar: DailyBar) -> Fill | None:
        """在给定 bar 上撮合，返回 None 表示当日不可成交（顺延/拒单由调用方决定）。"""


class NextDayOpenBroker(Broker):
    """T 日信号 → T+1 开盘价成交；涨停买不进、跌停卖不出、停牌不成交。"""

    def match(self, order: Order, bar: DailyBar) -> Fill | None:
        if bar is None or bar.suspended:
            return None
        up, down = limit_prices(bar.pre_close, self.cfg.board(bar.symbol))
        price = bar.open
        if order.side == Side.BUY and price >= up * 0.999:
            return None  # 开盘即涨停
        if order.side == Side.SELL and price <= down * 1.001:
            return None  # 开盘即跌停

        qty = order.remaining
        if self.cfg.volume_participation > 0 and bar.volume > 0:
            qty = min(qty, int(bar.volume * self.cfg.volume_participation) // 100 * 100)
            if qty <= 0:
                return None

        fill_price = self.cost.fill_price(order.side, price)
        commission, stamp_tax, transfer = self.cost.calc(order.side, fill_price, qty)
        return Fill(
            order_id=order.id or 0,
            symbol=bar.symbol,
            side=order.side,
            qty=qty,
            price=round(fill_price, 4),
            trade_date=bar.trade_date,
            commission=commission,
            stamp_tax=stamp_tax,
            transfer_fee=transfer,
        )


class CloseBroker(Broker):
    """T+1 收盘价成交（备选模型）。"""

    def match(self, order: Order, bar: DailyBar) -> Fill | None:
        if bar is None or bar.suspended:
            return None
        up, down = limit_prices(bar.pre_close, self.cfg.board(bar.symbol))
        price = bar.close
        if order.side == Side.BUY and bar.high >= up * 0.999:
            return None
        if order.side == Side.SELL and bar.low <= down * 1.001:
            return None
        fill_price = self.cost.fill_price(order.side, price)
        qty = order.remaining
        commission, stamp_tax, transfer = self.cost.calc(order.side, fill_price, qty)
        return Fill(order.id or 0, bar.symbol, order.side, qty, round(fill_price, 4),
                    bar.trade_date, commission, stamp_tax, transfer)


def broker_factory(name: str, cost_policy: CostPolicy, config: MatchConfig | None = None) -> Broker:
    return {"next_open": NextDayOpenBroker, "close": CloseBroker}[name](cost_policy, config)
