"""账户聚合：资金、持仓、盯市与不变量校验（SDD 4.2 / 7.5）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from conflex.domain.models import Fill, Side
from conflex.errors import InsufficientCash, InsufficientPosition

_EPS = 1e-6


@dataclass
class Position:
    symbol: str
    qty: int = 0
    available_qty: int = 0      # T+1 可用
    cost_price: float = 0.0
    last_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.qty * self.last_price

    @property
    def floating_pnl(self) -> float:
        return (self.last_price - self.cost_price) * self.qty


@dataclass
class CashBook:
    available: float = 0.0
    frozen: float = 0.0

    @property
    def total(self) -> float:
        return self.available + self.frozen


class Account:
    def __init__(self, id: int, name: str, initial_cash: float):
        self.id = id
        self.name = name
        self.cash = CashBook(available=initial_cash, frozen=0.0)
        self.positions: dict[str, Position] = {}
        self.initial_cash = initial_cash
        # 资金流水：(date, type, amount, order_id, balance_after)
        self.flows: list[tuple[date, str, float, int | None, float]] = []

    # ---- 资金 ----
    def freeze(self, amount: float, when: date, order_id: int | None = None):
        if amount > self.cash.available + _EPS:
            raise InsufficientCash(
                f"可用资金 {self.cash.available:.2f} 不足，需冻结 {amount:.2f}"
            )
        self.cash.available -= amount
        self.cash.frozen += amount
        self._flow(when, "freeze", -amount, order_id)

    def unfreeze(self, amount: float, when: date, order_id: int | None = None):
        amount = min(amount, self.cash.frozen)
        self.cash.frozen -= amount
        self.cash.available += amount
        self._flow(when, "unfreeze", amount, order_id)

    def deposit(self, amount: float, when: date):
        self.cash.available += amount
        self._flow(when, "in", amount, None)

    def _flow(self, when: date, kind: str, amount: float, order_id: int | None):
        self.flows.append((when, kind, amount, order_id, self.cash.total))

    # ---- 成交回补 ----
    def apply_fill(self, fill: Fill):
        pos = self.positions.setdefault(fill.symbol, Position(fill.symbol))
        if fill.side == Side.BUY:
            need = fill.qty * fill.price
            # 从冻结资金中划转
            take_frozen = min(self.cash.frozen, need + fill.fee)
            self.cash.frozen -= take_frozen
            paid = take_frozen
            if paid < need + fill.fee - _EPS:  # 冻结不足时从可用补
                extra = need + fill.fee - paid
                self.cash.available -= extra
                paid += extra
            total_cost = pos.cost_price * pos.qty + fill.qty * fill.price + fill.fee
            pos.qty += fill.qty  # 当日买入 available_qty 不增加（T+1）
            pos.cost_price = total_cost / pos.qty
            pos.last_price = fill.price
            self._flow(fill.trade_date, "buy", -paid, fill.order_id)
        else:
            if fill.qty > pos.available_qty:
                raise InsufficientPosition(
                    f"{fill.symbol} 可用 {pos.available_qty} 不足，卖出 {fill.qty}"
                )
            proceeds = fill.qty * fill.price - fill.fee
            pos.qty -= fill.qty
            pos.available_qty -= fill.qty
            pos.last_price = fill.price
            if pos.qty == 0:
                pos.cost_price = 0.0
            else:
                pos.cost_price = (pos.cost_price * (pos.qty + fill.qty) - fill.price * fill.qty) / pos.qty
            self.cash.available += proceeds
            self._flow(fill.trade_date, "sell", proceeds, fill.order_id)

    # ---- 盘后结算 ----
    def settle(self, close_prices: dict[str, float]):
        for symbol, pos in self.positions.items():
            if pos.qty > 0:
                pos.last_price = close_prices.get(symbol, pos.last_price)
        # T+1：当日买入在收盘后转为可用
        for pos in self.positions.values():
            pos.available_qty = pos.qty

    @property
    def market_value(self) -> float:
        return sum(p.market_value for p in self.positions.values() if p.qty > 0)

    @property
    def total_equity(self) -> float:
        return self.cash.total + self.market_value

    @property
    def floating_pnl(self) -> float:
        return self.total_equity - self.initial_cash
