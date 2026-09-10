"""事件驱动回测主循环（SDD 8.3）。

输入数据在构造时一次性注入（由 application 层从仓储读取），引擎本身不做任何 IO，
且策略只能通过 Context 取 <= 当前日 的数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from conflex.domain.backtest.clock import BacktestClock
from conflex.domain.backtest.metrics import compute_metrics
from conflex.domain.models import DailyBar, Fill, OrderStatus, OrderType, Side
from conflex.domain.portfolio.account import Account
from conflex.domain.portfolio.matcher import Broker
from conflex.domain.portfolio.order import Order
from conflex.domain.portfolio.rebalance import build_diff_orders


@dataclass
class BacktestConfig:
    start: str | pd.Timestamp
    end: str | pd.Timestamp
    initial_cash: float = 1_000_000.0
    account_name: str = "backtest"


@dataclass
class BacktestResult:
    equity: pd.Series
    benchmark: pd.Series | None
    trades: pd.DataFrame
    metrics: dict
    config: dict
    positions_history: pd.DataFrame


@dataclass
class Context:
    engine: "BacktestEngine"
    today: pd.Timestamp

    @property
    def account(self) -> Account:
        return self.engine.account

    def score_row(self, today) -> pd.Series:
        today = pd.Timestamp(today)
        frame = self.engine.scores
        visible = frame.loc[frame.index <= today]
        if visible.empty:
            return pd.Series(dtype=float)
        return visible.iloc[-1]

    def is_suspended(self, symbol: str, today) -> bool:
        df = self.engine.bars.get(symbol)
        t = pd.Timestamp(today)
        if df is None or t not in df.index:
            return True
        return bool(df.loc[t].get("suspended", False))

    def is_rebalance_day(self, freq: str) -> bool:
        return self.engine.is_rebalance_day(self.today, freq)

    def rebalance(self, target_weights: dict[str, float], signal_date=None):
        engine = self.engine
        current = {
            s: (p.qty, p.available_qty)
            for s, p in engine.account.positions.items()
            if p.qty > 0
        }
        prices = {s: float(df.loc[self.today, "close"])
                  for s, df in engine.bars.items() if self.today in df.index}
        drafts = build_diff_orders(
            current, target_weights, prices, engine.account.total_equity
        )
        for d in drafts:
            engine.place_order(
                symbol=d.symbol,
                side=d.side,
                qty=d.qty,
                signal_date=pd.Timestamp(signal_date or self.today),
                ref_price=prices.get(d.symbol),
            )


class BacktestEngine:
    def __init__(
        self,
        bars: dict[str, pd.DataFrame],
        scores: pd.DataFrame,
        strategy,
        broker: Broker,
        config: BacktestConfig,
        benchmark: pd.Series | None = None,
    ):
        self.bars = {s: df.sort_index() for s, df in bars.items()}
        self.scores = scores.sort_index()
        self.strategy = strategy
        self.broker = broker
        self.config = config
        self.benchmark = benchmark
        self.clock = BacktestClock(self._calendar())
        self.account = Account(id=0, name=config.account_name, initial_cash=config.initial_cash)
        self._pending: list[Order] = []
        self._frozen: dict[int, float] = {}
        self._oid = 0
        self._trades: list[dict] = []
        self._equity: list[tuple[pd.Timestamp, float]] = []
        self._pos_hist: list[dict] = []

    def _calendar(self) -> pd.DatetimeIndex:
        idx = pd.DatetimeIndex([])
        for df in self.bars.values():
            idx = idx.union(df.index)
        idx = idx[(idx >= pd.Timestamp(self.config.start)) & (idx <= pd.Timestamp(self.config.end))]
        return pd.DatetimeIndex(sorted(idx.unique()))

    # ---- 订单（T 日信号，次日成交）----
    def place_order(self, symbol: str, side: Side, qty: int,
                    signal_date: pd.Timestamp, ref_price: float | None):
        self._oid += 1
        order = Order(
            id=self._oid,
            account_id=self.account.id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            qty=qty,
            signal_date=signal_date.date(),
        )
        if side == Side.BUY and ref_price:
            # 按信号日收盘价上浮估损冻结，成交时先解冻再据实扣划
            est = qty * ref_price * 1.003
            try:
                self.account.freeze(est, when=signal_date.date(), order_id=order.id)
                self._frozen[order.id] = est
            except Exception:
                return  # 资金不足，弃单
        self._pending.append(order)

    def is_rebalance_day(self, day: pd.Timestamp, freq: str) -> bool:
        cal = self.clock._dates
        i = cal.get_loc(day)
        if freq == "D":
            return True
        if freq == "W":
            return i == len(cal) - 1 or cal[i + 1].week != day.week() or cal[i + 1] - day > pd.Timedelta(days=3)
        if freq == "M":
            return i == len(cal) - 1 or cal[i + 1].month != day.month
        return True

    def _bar_on(self, symbol: str, day: pd.Timestamp) -> DailyBar | None:
        df = self.bars.get(symbol)
        if df is None or day not in df.index:
            return None
        r = df.loc[day]
        return DailyBar(
            symbol=symbol,
            trade_date=day.date(),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r.get("volume", 0.0) or 0.0),
            amount=float(r.get("amount", 0.0) or 0.0),
            pre_close=float(r["pre_close"]) if pd.notna(r.get("pre_close")) else None,
            suspended=bool(r.get("suspended", False)),
        )

    def run(self) -> BacktestResult:
        self.strategy.on_start(Context(self, self.clock.now))
        last_day = None
        for day in self.clock:
            last_day = day
            # 1) 撮合昨日信号单（T+1）
            still_pending: list[Order] = []
            for order in self._pending:
                bar = self._bar_on(order.symbol, day)
                fill = self.broker.match(order, bar) if bar is not None else None
                if fill is None:
                    order.transition(OrderStatus.REJECTED)
                    if order.id in self._frozen:
                        self.account.unfreeze(self._frozen.pop(order.id), day.date(), order.id)
                    continue
                if order.id in self._frozen:
                    self.account.unfreeze(self._frozen.pop(order.id), day.date(), order.id)
                order.trade_date = day.date()
                order.apply_fill(fill.qty, fill.price)
                self.account.apply_fill(fill)
                self._trades.append(
                    {"trade_date": day, "symbol": order.symbol, "side": fill.side.value,
                     "qty": fill.qty, "price": fill.price, "fee": fill.fee,
                     "commission": fill.commission, "stamp_tax": fill.stamp_tax}
                )
            self._pending = still_pending

            # 2) 策略生成今日信号（只可见 <= day 的数据）
            ctx = Context(self, day)
            self.strategy.on_bar(ctx, day)

            # 3) 收盘结算
            close_prices = {}
            for s, df in self.bars.items():
                if day in df.index:
                    close_prices[s] = float(df.loc[day, "close"])
            self.account.settle(close_prices)
            self._equity.append((day, self.account.total_equity))
            for s, p in self.account.positions.items():
                if p.qty > 0:
                    self._pos_hist.append({"trade_date": day, "symbol": s,
                                           "qty": p.qty, "market_value": p.market_value,
                                           "weight": p.market_value / self.account.total_equity})

        for order in self._pending:  # 区间结束仍未成交
            if not order.status.is_final and order.id in self._frozen:
                self.account.unfreeze(self._frozen.pop(order.id), last_day.date(), order.id)
            order.transition(OrderStatus.CANCELLED)
        self.strategy.on_end(Context(self, last_day))

        equity = pd.Series(dict(self._equity), name="equity").sort_index()
        bench = self.benchmark.reindex(equity.index).ffill() if self.benchmark is not None else None
        metrics = compute_metrics(equity, bench)
        trades_df = pd.DataFrame(self._trades)
        metrics["total_fee"] = float(trades_df["fee"].sum()) if not trades_df.empty else 0.0
        metrics["trade_count"] = int(len(trades_df))
        metrics["final_equity"] = float(equity.iloc[-1]) if not equity.empty else self.config.initial_cash
        return BacktestResult(
            equity=equity,
            benchmark=bench,
            trades=trades_df,
            metrics=metrics,
            config={"start": str(self.config.start), "end": str(self.config.end),
                    "initial_cash": self.config.initial_cash, "strategy": self.strategy.name},
            positions_history=pd.DataFrame(self._pos_hist),
        )
