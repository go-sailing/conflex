"""A 股交易成本与滑点模型（SDD 7.2）。"""
from __future__ import annotations

from dataclasses import dataclass

from conflex.domain.models import Side


@dataclass(frozen=True)
class CostPolicy:
    commission_rate: float = 0.00025
    commission_min: float = 5.0
    stamp_tax_rate: float = 0.001   # 仅卖出
    transfer_fee_rate: float = 0.0
    slippage_bps: float = 5.0       # 1bp = 0.01%

    def fill_price(self, side: Side, raw_price: float) -> float:
        bps = self.slippage_bps / 10000.0
        return raw_price * (1 + bps) if side == Side.BUY else raw_price * (1 - bps)

    def calc(self, side: Side, price: float, qty: int) -> tuple[float, float, float]:
        """返回 (佣金, 印花税, 过户费)。"""
        amount = price * qty
        commission = max(amount * self.commission_rate, self.commission_min)
        stamp_tax = amount * self.stamp_tax_rate if side == Side.SELL else 0.0
        transfer_fee = amount * self.transfer_fee_rate
        return round(commission, 4), round(stamp_tax, 4), round(transfer_fee, 4)
