"""目标持仓 → 买卖差价单（SDD 7.4）。"""
from __future__ import annotations

from dataclasses import dataclass

from conflex.domain.models import OrderType, Side


@dataclass
class OrderDraft:
    symbol: str
    side: Side
    qty: int
    order_type: OrderType = OrderType.MARKET
    reason: str = ""


def build_diff_orders(
    current: dict[str, tuple[int, float]],
    target_weights: dict[str, float],
    prices: dict[str, float],
    total_equity: float,
    max_position: int | None = None,
    max_weight: float = 1.0,
) -> list[OrderDraft]:
    """current: symbol -> (持仓量, 可用量)；目标权重按总资产折算股数（100 整手）。

    先卖后买，保证买入资金由卖出释放。
    """
    target_symbols = set(target_weights)
    if max_position:
        target_symbols = set(list(target_weights)[:max_position])

    target_qty: dict[str, int] = {}
    for sym in target_symbols:
        price = prices.get(sym, 0)
        w = min(target_weights[sym], max_weight)
        if price <= 0:
            continue
        target_qty[sym] = int(total_equity * w / price // 100 * 100)

    drafts: list[OrderDraft] = []

    # 1) 卖出：不在目标中或需减仓
    for sym, (qty, available) in current.items():
        tgt = target_qty.get(sym, 0)
        diff = qty - tgt
        if diff > 0:
            # 减仓受 T+1 可用量约束；清仓时允许卖出可用部分
            sell_qty = min(diff, available) if tgt > 0 else available
            if sell_qty > 0:
                drafts.append(OrderDraft(sym, Side.SELL, _round_lot(sell_qty, tgt == 0)))

    # 2) 买入：新开仓或加仓
    for sym, tgt in target_qty.items():
        cur = current.get(sym, (0, 0))[0]
        diff = tgt - cur
        if diff > 0:
            drafts.append(OrderDraft(sym, Side.BUY, (diff // 100) * 100))

    return [d for d in drafts if d.qty > 0]


def _round_lot(qty: int, clear: bool) -> int:
    """清仓可零股，其余按 100 整手。"""
    return qty if clear else (qty // 100) * 100
