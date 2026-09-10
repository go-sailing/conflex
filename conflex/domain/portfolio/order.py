"""订单实体与成交状态机（SDD 7.1）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from conflex.domain.models import OrderStatus, OrderType, Side
from conflex.errors import InvalidOrderTransition

_ALLOWED = {
    OrderStatus.PENDING: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
                          OrderStatus.CANCELLED, OrderStatus.REJECTED},
    OrderStatus.PARTIALLY_FILLED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
                                   OrderStatus.CANCELLED},
}


@dataclass
class Order:
    id: int | None
    account_id: int
    symbol: str
    side: Side
    order_type: OrderType
    qty: int
    limit_price: float | None = None
    filled_qty: int = 0
    avg_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    signal_date: date | None = None
    trade_date: date | None = None

    def transition(self, target: OrderStatus):
        if target == self.status:
            return
        allowed = _ALLOWED.get(self.status, set())
        if target not in allowed:
            raise InvalidOrderTransition(f"{self.status} -> {target}")
        self.status = target

    @property
    def remaining(self) -> int:
        return self.qty - self.filled_qty

    def apply_fill(self, qty: int, price: float):
        new_filled = self.filled_qty + qty
        if new_filled > self.qty:
            raise InvalidOrderTransition("成交数量超过委托数量")
        self.avg_price = (self.avg_price * self.filled_qty + price * qty) / new_filled
        self.filled_qty = new_filled
        self.transition(
            OrderStatus.FILLED if new_filled >= self.qty else OrderStatus.PARTIALLY_FILLED
        )
