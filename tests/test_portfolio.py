"""模拟持仓：费用、账户不变量、T+1、订单状态机、调仓差价单。"""
from __future__ import annotations

from datetime import date

from conflex.domain.models import Fill, OrderStatus, OrderType, Side
from conflex.domain.portfolio.account import Account
from conflex.domain.portfolio.cost import CostPolicy
from conflex.domain.portfolio.order import Order
from conflex.domain.portfolio.rebalance import build_diff_orders
from conflex.errors import InsufficientCash, InvalidOrderTransition


def test_cost_policy():
    policy = CostPolicy()
    # 买入 1000 股 *10 元 = 10000，佣金万2.5=2.5 → 最低 5 元，无印花税
    commission, stamp, _ = policy.calc(Side.BUY, 10.0, 1000)
    assert commission == 5.0 and stamp == 0.0
    # 卖出 1000 股 *10 元：佣金 5 元 + 印花税 10 元
    commission, stamp, _ = policy.calc(Side.SELL, 10.0, 1000)
    assert commission == 5.0 and stamp == 10.0
    # 滑点方向：买高卖低
    assert policy.fill_price(Side.BUY, 10.0) > 10.0
    assert policy.fill_price(Side.SELL, 10.0) < 10.0


def test_account_buy_tplus1_and_settle():
    acc = Account(id=1, name="t", initial_cash=100_000)
    acc.freeze(11_000, date(2024, 1, 2))
    assert acc.cash.available == 89_000 and acc.cash.frozen == 11_000
    try:
        acc.freeze(100_000, date(2024, 1, 2))
        assert False, "应拒绝超额冻结"
    except InsufficientCash:
        pass

    order = Order(id=1, account_id=1, symbol="600519.SH", side=Side.BUY,
                  order_type=OrderType.MARKET, qty=1000, signal_date=date(2024, 1, 2))
    acc.unfreeze(11_000, date(2024, 1, 3), 1)
    fill = Fill(order_id=1, symbol="600519.SH", side=Side.BUY, qty=1000,
                price=10.0005, trade_date=date(2024, 1, 3), commission=5.0)
    order.apply_fill(1000, 10.0005)
    acc.apply_fill(fill)
    pos = acc.positions["600519.SH"]
    assert pos.qty == 1000 and pos.available_qty == 0  # T+1 当日不可卖
    # 卖出可用量为 0 → 拒绝
    try:
        acc.apply_fill(Fill(2, "600519.SH", Side.SELL, 1000, 10.0, date(2024, 1, 3)))
        assert False
    except Exception:
        pass
    acc.settle({"600519.SH": 10.5})
    assert pos.available_qty == 1000
    assert abs(pos.market_value - 10_500) < 1e-6
    assert acc.total_equity > 100_000  # 盈利


def test_order_state_machine():
    o = Order(id=1, account_id=1, symbol="X", side=Side.BUY,
              order_type=OrderType.MARKET, qty=200)
    o.apply_fill(100, 10.0)
    assert o.status == OrderStatus.PARTIALLY_FILLED and o.remaining == 100
    o.apply_fill(100, 10.1)
    assert o.status == OrderStatus.FILLED and abs(o.avg_price - 10.05) < 1e-9
    bad = Order(id=2, account_id=1, symbol="Y", side=Side.BUY,
                order_type=OrderType.MARKET, qty=100)
    bad.transition(OrderStatus.FILLED)
    try:
        bad.transition(OrderStatus.PENDING)
        assert False
    except InvalidOrderTransition:
        pass


def test_build_diff_orders_sells_first():
    # 持有 A 200 股、B 300 股；目标只有 A
    current = {"A": (200, 200), "B": (300, 300)}
    drafts = build_diff_orders(
        current, {"A": 1.0}, {"A": 10.0, "B": 20.0}, total_equity=100_000)
    sides = [(d.symbol, d.side.value) for d in drafts]
    assert ("B", "sell") in sides and ("A", "buy") in sides
    assert [s for s in sides].index(("B", "sell")) < sides.index(("A", "buy"))
    # 买入数量为 100 整手
    buy = next(d for d in drafts if d.symbol == "A")
    assert buy.qty % 100 == 0
