"""账户/订单/成交/策略/回测结果仓储（SDD 7、10.2）。"""
from __future__ import annotations

import json
from datetime import date, datetime

from conflex.domain.models import Fill, OrderStatus, OrderType, Side
from conflex.domain.portfolio.account import Account, Position
from conflex.domain.portfolio.order import Order


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TradingRepository:
    def __init__(self, db):
        self.db = db

    # ---- 账户 ----
    def create_account(self, name: str, initial_cash: float) -> int:
        cur = self.db.execute(
            "INSERT INTO account(name,initial_cash,cash_available,cash_frozen,created_at)"
            " VALUES(?,?,?,?,?)",
            (name, initial_cash, initial_cash, 0.0, _now()),
        )
        return cur.lastrowid

    def list_accounts(self) -> list[dict]:
        return [dict(r) for r in self.db.query(
            """SELECT a.*, COALESCE(SUM(p.qty*p.last_price),0) AS market_value
               FROM account a LEFT JOIN position p ON p.account_id=a.id
               GROUP BY a.id ORDER BY a.id""")]

    def get_account(self, account_id: int) -> Account | None:
        row = self.db.query_one("SELECT * FROM account WHERE id=?", (account_id,))
        if not row:
            return None
        acc = Account(id=row["id"], name=row["name"], initial_cash=row["initial_cash"])
        acc.cash.available = row["cash_available"]
        acc.cash.frozen = row["cash_frozen"]
        for p in self.db.query("SELECT * FROM position WHERE account_id=?", (account_id,)):
            acc.positions[p["symbol"]] = Position(
                symbol=p["symbol"], qty=p["qty"], available_qty=p["available_qty"],
                cost_price=p["cost_price"], last_price=p["last_price"] or 0.0)
        # 已落库流水不重复写入
        count = self.db.query_one(
            "SELECT COUNT(*) c FROM cash_flow WHERE account_id=?", (account_id,))["c"]
        acc._flushed = count
        return acc

    def save_order(self, order: Order) -> int:
        if order.id is None:
            cur = self.db.execute(
                """INSERT INTO "order"(account_id,symbol,side,order_type,qty,filled_qty,
                   avg_price,status,signal_date,trade_date,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order.account_id, order.symbol, order.side.value, order.order_type.value,
                 order.qty, order.filled_qty, order.avg_price, order.status.value,
                 order.signal_date.isoformat() if order.signal_date else None,
                 order.trade_date.isoformat() if order.trade_date else None,
                 _now(), _now()))
            order.id = cur.lastrowid
        else:
            self.db.execute(
                """UPDATE "order" SET filled_qty=?,avg_price=?,status=?,trade_date=?,updated_at=?
                   WHERE id=?""",
                (order.filled_qty, order.avg_price, order.status.value,
                 order.trade_date.isoformat() if order.trade_date else None, _now(), order.id))
        return order.id

    def persist_cash(self, account: Account):
        self.db.execute(
            "UPDATE account SET cash_available=?,cash_frozen=? WHERE id=?",
            (account.cash.available, account.cash.frozen, account.id))
        self._flush_flows(account)

    def _flush_flows(self, account: Account):
        start = getattr(account, "_flushed", 0)
        for when, kind, amount, order_id, balance in account.flows[start:]:
            self.db.execute(
                """INSERT INTO cash_flow(account_id,type,amount,ref_order_id,occur_date,balance_after)
                   VALUES(?,?,?,?,?,?)""",
                (account.id, kind, amount, order_id,
                 when.isoformat() if hasattr(when, "isoformat") else str(when), balance))
        account._flushed = len(account.flows)

    def persist_fill(self, account: Account, order: Order, fill: Fill):
        self.save_order(order)
        self.db.execute(
            """INSERT INTO trade(order_id,account_id,symbol,side,qty,price,
               commission,stamp_tax,transfer_fee,trade_date)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (order.id, account.id, fill.symbol, fill.side.value, fill.qty, fill.price,
             fill.commission, fill.stamp_tax, fill.transfer_fee, fill.trade_date.isoformat()))
        self._sync_positions(account, fill.symbol)
        self.db.execute(
            "UPDATE account SET cash_available=?,cash_frozen=? WHERE id=?",
            (account.cash.available, account.cash.frozen, account.id))
        self._flush_flows(account)

    def _sync_positions(self, account: Account, symbol: str):
        pos = account.positions.get(symbol)
        if not pos or pos.qty == 0:
            self.db.execute(
                "DELETE FROM position WHERE account_id=? AND symbol=?", (account.id, symbol))
            return
        self.db.execute(
            """INSERT INTO position(account_id,symbol,qty,available_qty,cost_price,last_price)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(account_id,symbol) DO UPDATE SET qty=excluded.qty,
                 available_qty=excluded.available_qty,cost_price=excluded.cost_price,
                 last_price=excluded.last_price""",
            (account.id, symbol, pos.qty, pos.available_qty, pos.cost_price, pos.last_price))

    def persist_settlement(self, account: Account, day: date):
        for symbol, pos in account.positions.items():
            self._sync_positions(account, symbol)
        self.db.execute(
            """INSERT INTO account_snapshot(account_id,trade_date,cash,market_value,total_equity)
               VALUES(?,?,?,?,?)
               ON CONFLICT(account_id,trade_date) DO UPDATE SET cash=excluded.cash,
                 market_value=excluded.market_value,total_equity=excluded.total_equity""",
            (account.id, day.isoformat(), account.cash.total,
             account.market_value, account.total_equity))

    def orders(self, account_id: int, status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM \"order\" WHERE account_id=?"
        params: list = [account_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY id DESC"
        return [dict(r) for r in self.db.query(sql, tuple(params))]

    def trades(self, account_id: int) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM trade WHERE account_id=? ORDER BY id DESC", (account_id,))]

    def cash_flows(self, account_id: int) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM cash_flow WHERE account_id=? ORDER BY id", (account_id,))]

    def snapshots(self, account_id: int) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM account_snapshot WHERE account_id=? ORDER BY trade_date", (account_id,))]

    def reconstruct_order(self, row: dict) -> Order:
        return Order(
            id=row["id"], account_id=row["account_id"], symbol=row["symbol"],
            side=Side(row["side"]), order_type=OrderType(row["order_type"]),
            qty=row["qty"], filled_qty=row["filled_qty"], avg_price=row["avg_price"] or 0.0,
            status=OrderStatus(row["status"]),
            signal_date=date.fromisoformat(row["signal_date"]) if row["signal_date"] else None,
            trade_date=date.fromisoformat(row["trade_date"]) if row["trade_date"] else None)

    # ---- 策略 ----
    def save_strategy(self, name: str, factors: list[dict], weighting: str,
                      rules: dict, rebalance_freq: str, strategy_id: int | None = None) -> int:
        if strategy_id:
            self.db.execute(
                """UPDATE strategy SET name=?,factors_json=?,weighting=?,rules_json=?,
                   rebalance_freq=?,updated_at=? WHERE id=?""",
                (name, json.dumps(factors, ensure_ascii=False), weighting,
                 json.dumps(rules, ensure_ascii=False), rebalance_freq, _now(), strategy_id))
            return strategy_id
        cur = self.db.execute(
            """INSERT INTO strategy(name,factors_json,weighting,rules_json,rebalance_freq,
               created_at,updated_at) VALUES(?,?,?,?,?,?,?)""",
            (name, json.dumps(factors, ensure_ascii=False), weighting,
             json.dumps(rules, ensure_ascii=False), rebalance_freq, _now(), _now()))
        return cur.lastrowid

    def list_strategies(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM strategy ORDER BY id")
        out = []
        for r in rows:
            d = dict(r)
            d["factors"] = json.loads(r["factors_json"])
            d["rules"] = json.loads(r["rules_json"])
            out.append(d)
        return out

    def get_strategy(self, strategy_id: int) -> dict | None:
        r = self.db.query_one("SELECT * FROM strategy WHERE id=?", (strategy_id,))
        if not r:
            return None
        d = dict(r)
        d["factors"] = json.loads(r["factors_json"])
        d["rules"] = json.loads(r["rules_json"])
        return d

    def delete_strategy(self, strategy_id: int):
        self.db.execute("DELETE FROM strategy WHERE id=?", (strategy_id,))

    # ---- 回测结果 ----
    def create_backtest_run(self, name: str, params: dict, start: str, end: str,
                            benchmark: str, status: str = "running") -> int:
        cur = self.db.execute(
            """INSERT INTO backtest_run(name,params_json,start_date,end_date,benchmark,
               data_version,code_version,status,created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (name, json.dumps(params, ensure_ascii=False), start, end, benchmark,
             params.get("data_version", ""), params.get("code_version", ""), status, _now()))
        return cur.lastrowid

    def finish_backtest_run(self, run_id: int, status: str, metrics: dict):
        self.db.execute(
            "UPDATE backtest_run SET status=?,metrics_json=?,finished_at=? WHERE id=?",
            (status, json.dumps(metrics, ensure_ascii=False), _now(), run_id))

    def save_equity(self, run_id: int, equity, benchmark, drawdown):
        rows = []
        for dt, val in equity.items():
            b = float(benchmark.loc[dt]) if benchmark is not None and dt in benchmark.index else None
            rows.append((run_id, dt.date().isoformat(), float(val), b,
                         float(drawdown.loc[dt]) if dt in drawdown.index else None))
        self.db.executemany(
            """INSERT INTO backtest_equity(run_id,trade_date,equity,benchmark,drawdown)
               VALUES(?,?,?,?,?)""", rows)

    def save_backtest_trades(self, run_id: int, trades):
        if trades is None or trades.empty:
            return
        rows = [
            (run_id, r["trade_date"].date().isoformat(), r["symbol"], r["side"],
             int(r["qty"]), float(r["price"]), float(r["fee"]))
            for _, r in trades.iterrows()
        ]
        self.db.executemany(
            "INSERT INTO backtest_trade(run_id,trade_date,symbol,side,qty,price,fee) "
            "VALUES(?,?,?,?,?,?,?)", rows)

    def list_backtests(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM backtest_run ORDER BY id DESC")
        out = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(r["metrics_json"]) if r["metrics_json"] else None
            d["params"] = json.loads(r["params_json"])
            out.append(d)
        return out

    def get_backtest(self, run_id: int) -> dict | None:
        r = self.db.query_one("SELECT * FROM backtest_run WHERE id=?", (run_id,))
        if not r:
            return None
        d = dict(r)
        d["metrics"] = json.loads(r["metrics_json"]) if r["metrics_json"] else None
        d["equity"] = [dict(x) for x in self.db.query(
            "SELECT trade_date,equity,benchmark,drawdown FROM backtest_equity WHERE run_id=?",
            (run_id,))]
        d["trades"] = [dict(x) for x in self.db.query(
            "SELECT trade_date,symbol,side,qty,price,fee FROM backtest_trade WHERE run_id=?",
            (run_id,))]
        return d
