"""模拟持仓应用服务：下单、T+1 撮合、目标调仓、盘后结算（SDD 7）。"""
from __future__ import annotations

from datetime import date

import pandas as pd

from conflex.config import Settings
from conflex.domain.models import DailyBar, OrderType, Side
from conflex.domain.portfolio.account import Account
from conflex.domain.portfolio.cost import CostPolicy
from conflex.domain.portfolio.matcher import (
    MatchConfig, NextDayOpenBroker, broker_factory,
)
from conflex.domain.portfolio.order import Order
from conflex.domain.portfolio.rebalance import build_diff_orders
from conflex.errors import ConflexError


class PaperService:
    def __init__(self, trading_repo, market_repo, settings: Settings, broker_name: str = "next_open"):
        self.tr = trading_repo
        self.mr = market_repo
        self.settings = settings
        self.cost = CostPolicy(
            commission_rate=settings.commission_rate,
            commission_min=settings.commission_min,
            stamp_tax_rate=settings.stamp_tax_rate,
            slippage_bps=settings.slippage_bps,
        )
        self.broker = broker_factory(broker_name, self.cost)

    # ---- 账户 ----
    def create_account(self, name: str, initial_cash: float) -> int:
        return self.tr.create_account(name, initial_cash)

    def list_accounts(self):
        return self.tr.list_accounts()

    def _account(self, account_id: int) -> Account:
        acc = self.tr.get_account(account_id)
        if acc is None:
            raise ConflexError(f"账户不存在: {account_id}")
        return acc

    def positions(self, account_id: int) -> list[dict]:
        acc = self._account(account_id)
        out = []
        for s, p in acc.positions.items():
            out.append({"symbol": s, "qty": p.qty, "available_qty": p.available_qty,
                        "cost_price": round(p.cost_price, 4),
                        "last_price": round(p.last_price, 4),
                        "market_value": round(p.market_value, 2),
                        "floating_pnl": round(p.floating_pnl, 2)})
        return out

    def latest_close(self, symbol: str, on: date) -> float | None:
        df = self.mr.read(symbol, None, on)
        if df.empty:
            return None
        return float(df.iloc[-1]["close"])

    # ---- 下单（T 日信号，次日成交）----
    def submit_order(self, account_id: int, symbol: str, side: str, qty: int,
                     signal_date: date | None = None) -> dict:
        acc = self._account(account_id)
        order = Order(id=None, account_id=account_id, symbol=symbol,
                      side=Side(side), order_type=OrderType.MARKET, qty=int(qty),
                      signal_date=signal_date or date.today())
        if order.side == Side.BUY:
            ref = self.latest_close(symbol, signal_date or date.today())
            if not ref:
                raise ConflexError(f"{symbol} 无可用行情，无法冻结资金")
            est = qty * ref * 1.003
            acc.freeze(est, when=order.signal_date)
            self.tr.persist_cash(acc)
        self.tr.save_order(order)
        return {"order_id": order.id, "status": order.status.value}

    def cancel_order(self, account_id: int, order_id: int) -> dict:
        from conflex.domain.models import OrderStatus
        rows = self.tr.orders(account_id)
        row = next((r for r in rows if r["id"] == order_id), None)
        if not row:
            raise ConflexError("订单不存在")
        order = self.tr.reconstruct_order(row)
        if order.status != OrderStatus.PENDING:
            raise ConflexError(f"仅待报订单可撤，当前 {order.status.value}")
        acc = self._account(account_id)
        if order.side == Side.BUY:
            est = order.qty * (self.latest_close(order.symbol, order.signal_date) or 0) * 1.003
            acc.unfreeze(est, when=date.today(), order_id=order.id)
            self.tr.persist_cash(acc)
        order.transition(OrderStatus.CANCELLED)
        self.tr.save_order(order)
        return {"order_id": order.id, "status": order.status.value}

    def _bar(self, symbol: str, day: date) -> DailyBar | None:
        df = self.mr.read(symbol, day, day)
        if df.empty:
            return None
        r = df.iloc[0]
        return DailyBar(symbol=symbol, trade_date=pd.Timestamp(r["trade_date"]).date(),
                        open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                        close=float(r["close"]), volume=float(r.get("volume", 0) or 0),
                        pre_close=float(r["pre_close"]) if pd.notna(r.get("pre_close")) else None,
                        suspended=bool(r.get("suspended", False)))

    def run_market_day(self, account_id: int, day: date) -> dict:
        """T+1 开盘撮合待报订单，然后按收盘价结算。"""
        acc = self._account(account_id)
        pending = [self.tr.reconstruct_order(r)
                   for r in self.tr.orders(account_id, status="pending")]
        filled, rejected = 0, 0
        for order in pending:
            bar = self._bar(order.symbol, day)
            fill = self.broker.match(order, bar) if bar else None
            if fill is None:
                from conflex.domain.models import OrderStatus
                order.transition(OrderStatus.REJECTED)
                if order.side == Side.BUY:
                    est = order.qty * (bar.open if bar else 0) * 1.003
                    acc.unfreeze(est, when=day, order_id=order.id)
                    self.tr.persist_cash(acc)
                self.tr.save_order(order)
                rejected += 1
                continue
            if order.side == Side.BUY:
                est = order.qty * (self.latest_close(order.symbol, order.signal_date) or bar.open) * 1.003
                acc.unfreeze(est, when=day, order_id=order.id)
            order.trade_date = day
            order.apply_fill(fill.qty, fill.price)
            acc.apply_fill(fill)
            self.tr.persist_fill(acc, order, fill)
            filled += 1

        closes = {}
        for sym in list(acc.positions.keys()):
            bar = self._bar(sym, day)
            if bar:
                closes[sym] = bar.close
        acc.settle(closes)
        self.tr.persist_settlement(acc, day)
        return {"date": day.isoformat(), "filled": filled, "rejected": rejected,
                "total_equity": round(acc.total_equity, 2)}

    # ---- 目标调仓 ----
    def rebalance_preview(self, account_id: int, target_weights: dict[str, float],
                          on: date | None = None) -> list[dict]:
        acc = self._account(account_id)
        on = on or date.today()
        current = {s: (p.qty, p.available_qty) for s, p in acc.positions.items() if p.qty > 0}
        prices = {s: (self.latest_close(s, on) or 0.0) for s in
                  set(current) | set(target_weights)}
        drafts = build_diff_orders(current, target_weights, prices, acc.total_equity)
        return [{"symbol": d.symbol, "side": d.side.value, "qty": d.qty} for d in drafts]

    def rebalance_commit(self, account_id: int, target_weights: dict[str, float],
                         on: date | None = None) -> dict:
        drafts = self.rebalance_preview(account_id, target_weights, on)
        ids = []
        for d in drafts:
            ids.append(self.submit_order(account_id, d["symbol"], d["side"], d["qty"],
                                         signal_date=on)["order_id"])
        return {"orders": ids}

    def equity_curve(self, account_id: int) -> list[dict]:
        return self.tr.snapshots(account_id)

    def orders(self, account_id: int, status: str | None = None):
        return self.tr.orders(account_id, status)

    def trades(self, account_id: int):
        return self.tr.trades(account_id)
