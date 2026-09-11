"""行情/证券主数据/数据源统计仓储（SDD 5.4、10.2）。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from conflex.domain.models import Instrument
from conflex.infra.storage.parquet_store import ParquetStore


class MarketRepository:
    def __init__(self, db, market_dir: Path):
        self.db = db
        self.store = ParquetStore(market_dir)

    # ---- cache_meta + Parquet ----
    def coverage(self, symbol: str) -> tuple[date, date] | None:
        row = self.db.query_one(
            "SELECT start_date,end_date FROM cache_meta WHERE symbol=? AND adj_type='none'",
            (symbol,),
        )
        if not row:
            return None
        return date.fromisoformat(row["start_date"]), date.fromisoformat(row["end_date"])

    def next_gap(
        self, symbol: str, start: date | None, end: date
    ) -> tuple[date, date] | None:
        cov = self.coverage(symbol)
        if cov is None:
            return (start, end) if start else None
        _, cov_end = cov
        if cov_end >= end:
            return None
        gap_start = max(start or cov_end, cov_end + timedelta(days=1))
        return (gap_start, end) if gap_start <= end else None

    def read(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        adjust: str = "none",
    ) -> pd.DataFrame:
        df = self.store.read(symbol, start, end)
        if df.empty or adjust == "none":
            return df
        return self._apply_adjust(symbol, df, adjust)

    def _apply_adjust(self, symbol: str, df: pd.DataFrame, adjust: str) -> pd.DataFrame:
        adj = self.store.read_adjust(symbol)
        if adj.empty:
            return df
        df = df.copy()
        merged = df.merge(adj, on="trade_date", how="left")
        merged["factor"] = merged["factor"].ffill().fillna(1.0)
        if adjust == "qfq":
            ref = merged["factor"].iloc[-1]
        else:  # hfq 以最早因子为基准
            ref = merged["factor"].iloc[0]
        ratio = merged["factor"] / ref
        for col in ("open", "high", "low", "close", "pre_close"):
            if col in merged.columns:
                merged[col] = (merged[col] * ratio).round(4)
        return merged.drop(columns=["factor"])

    def read_many(self, symbols, start=None, end=None, adjust: str = "none") -> dict:
        return {s: self.read(s, start, end, adjust) for s in symbols}

    def upsert(self, symbol: str, df: pd.DataFrame, is_final: bool = False,
               source: str = "") -> None:
        if df is None or df.empty:
            return
        self.store.upsert(symbol, df)
        # 更新缓存覆盖区间
        full = self.store.read(symbol)
        start_d = pd.Timestamp(full["trade_date"].min()).date().isoformat()
        end_d = pd.Timestamp(full["trade_date"].max()).date().isoformat()
        final_flag = 1 if is_final else 0
        self.db.execute(
            """INSERT INTO cache_meta(symbol,freq,start_date,end_date,is_final,adj_type,source,updated_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(symbol,freq,adj_type) DO UPDATE SET
                 start_date=excluded.start_date, end_date=excluded.end_date,
                 is_final=MAX(cache_meta.is_final, excluded.is_final),
                 source=excluded.source, updated_at=excluded.updated_at""",
            (symbol, "daily", start_d, end_d, final_flag, "none", source,
             datetime.now().isoformat(timespec="seconds")),
        )

    def upsert_adjust(self, symbol: str, df: pd.DataFrame) -> None:
        self.store.upsert_adjust(symbol, df)

    def coverage_rows(self) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT symbol,start_date,end_date,is_final,source,updated_at FROM cache_meta ORDER BY symbol")]

    def coverage_rows_page(self, page: int = 1, size: int = 50, keyword: str = "") -> tuple[list[dict], int]:
        where = ""
        params: list = []
        if keyword:
            where = "WHERE c.symbol LIKE ? OR i.name LIKE ?"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        total = self.db.query_one(
            "SELECT COUNT(*) as cnt FROM cache_meta c "
            "LEFT JOIN instrument i ON i.symbol = c.symbol " + where,
            tuple(params))["cnt"]
        offset = (page - 1) * size
        rows = [dict(r) for r in self.db.query(
            "SELECT c.symbol AS symbol, c.start_date, c.end_date, c.is_final, "
            "c.source, c.updated_at, i.name AS name, i.board AS board "
            "FROM cache_meta c LEFT JOIN instrument i ON i.symbol = c.symbol "
            f"{where} ORDER BY c.symbol LIMIT ? OFFSET ?",
            tuple(params) + (size, offset))]
        # 附带最新一根日线（最新价/涨跌幅），每页仅少量行，读取成本可控
        for r in rows:
            bar = self.store.latest_bar(r["symbol"])
            if bar:
                r["last_date"] = bar["trade_date"]
                r["last_close"] = bar.get("close")
                r["change_pct"] = bar.get("change_pct")
            else:
                r["last_date"] = r["last_close"] = r["change_pct"] = None
        return rows, total

    def get_instrument(self, symbol: str) -> Instrument | None:
        row = self.db.query_one("SELECT * FROM instrument WHERE symbol=?", (symbol,))
        if not row:
            return None
        return Instrument(
            symbol=row["symbol"], name=row["name"], exchange=row["exchange"],
            board=row["board"] or "main",
            list_date=date.fromisoformat(row["list_date"]),
            delist_date=date.fromisoformat(row["delist_date"]) if row["delist_date"] else None,
            is_st=bool(row["is_st"]),
        )

    def symbols_on_disk(self) -> list[str]:
        return self.store.symbols()

    def storage_bytes(self) -> int:
        return self.store.storage_bytes()

    # ---- instruments ----
    def load_instruments(self) -> list[Instrument]:
        rows = self.db.query("SELECT * FROM instrument ORDER BY symbol")
        return [
            Instrument(
                symbol=r["symbol"], name=r["name"], exchange=r["exchange"],
                board=r["board"] or "main",
                list_date=date.fromisoformat(r["list_date"]),
                delist_date=date.fromisoformat(r["delist_date"]) if r["delist_date"] else None,
                is_st=bool(r["is_st"]),
            )
            for r in rows
        ]

    def save_instruments(self, instruments: list[Instrument]) -> None:
        rows = [
            (i.symbol, i.name, i.exchange, i.board, i.list_date.isoformat(),
             i.delist_date.isoformat() if i.delist_date else None, int(i.is_st))
            for i in instruments
        ]
        self.db.executemany(
            """INSERT INTO instrument(symbol,name,exchange,board,list_date,delist_date,is_st)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(symbol) DO UPDATE SET
                 name=excluded.name, delist_date=excluded.delist_date, is_st=excluded.is_st""",
            rows,
        )

    def listed_symbols(self, day: date | None = None) -> list[str]:
        day = day or date.today()
        rows = self.db.query(
            "SELECT symbol FROM instrument WHERE list_date<=? AND (delist_date IS NULL OR delist_date>?)",
            (day.isoformat(), day.isoformat()),
        )
        return [r["symbol"] for r in rows]

    # ---- 股票池 ----
    # 板块池按交易所代码段精确筛选（instrument.board 由数据源引导时生成，
    # 对 ETF/指数等并不可靠，故板块判定一律走代码段）；
    # 指数池（sz50/hs300/zz500/zz1000）取 index_member 表中缓存的真实成分股。
    UNIVERSES: dict[str, str] = {
        "all": "全部A股",
        "main": "主板",
        "chinext": "创业板",
        "star": "科创板",
        "sz50": "上证50",
        "hs300": "沪深300",
        "zz500": "中证500",
        "zz1000": "中证1000",
    }

    # 股票池名 → 中证/上证指数代码
    INDEX_POOL_CODES: dict[str, str] = {
        "sz50": "000016",
        "hs300": "000300",
        "zz500": "000905",
        "zz1000": "000852",
    }

    @staticmethod
    def is_a_share(symbol: str) -> bool:
        """按代码段判断是否为沪深京 A 股个股（排除指数/ETF/可转债等）。"""
        code, _, exch = symbol.partition(".")
        if exch == "SH":
            return code[:3] in ("600", "601", "603", "605", "688", "689")
        if exch == "SZ":
            return code[:3] in ("000", "001", "002", "003", "300", "301", "302")
        if exch == "BJ":
            return code[:1] in ("8", "4", "9")
        return False

    def resolve_universe(self, name: str, day: date | None = None) -> list[str]:
        """根据预定义池返回存续股票代码列表（仅个股，不含指数/基金/债券）。"""
        day = day or date.today()
        base_sql = ("SELECT symbol FROM instrument "
                    "WHERE list_date<=? AND (delist_date IS NULL OR delist_date>?)")
        params: list = [day.isoformat(), day.isoformat()]

        def listed(clause: str | None = None) -> list[str]:
            sql = base_sql + (f" AND ({clause})" if clause else "")
            return [r["symbol"] for r in self.db.query(sql, tuple(params))]

        if name in self.INDEX_POOL_CODES:
            index_code = self.INDEX_POOL_CODES[name]
            rows = self.db.query(
                "SELECT symbol FROM index_member WHERE index_code=?", (index_code,))
            return [r["symbol"] for r in rows]
        if name == "all":
            return [s for s in listed() if self.is_a_share(s)]
        if name == "main":
            return listed(
                "(symbol LIKE '600%.SH' OR symbol LIKE '601%.SH' OR symbol LIKE '603%.SH' "
                "OR symbol LIKE '605%.SH' OR symbol LIKE '000%.SZ' OR symbol LIKE '001%.SZ' "
                "OR symbol LIKE '002%.SZ' OR symbol LIKE '003%.SZ')")
        if name == "star":
            return listed("symbol LIKE '688%.SH' OR symbol LIKE '689%.SH'")
        if name == "chinext":
            return listed("symbol LIKE '300%.SZ' OR symbol LIKE '301%.SZ' OR symbol LIKE '302%.SZ'")
        # 未知名称回退全部 A 股
        return [s for s in listed() if self.is_a_share(s)]

    # ---- 指数成分股缓存 ----
    def replace_index_members(self, index_code: str,
                              members: list[tuple[str, str]], updated_at: str) -> None:
        with self.db.lock:
            self.db.execute("DELETE FROM index_member WHERE index_code=?", (index_code,))
            self.db.executemany(
                "INSERT INTO index_member(index_code,symbol,name,updated_at) VALUES(?,?,?,?)",
                [(index_code, sym, nm, updated_at) for sym, nm in members])

    def index_member_updated_at(self, index_code: str) -> datetime | None:
        row = self.db.query_one(
            "SELECT MAX(updated_at) AS u FROM index_member WHERE index_code=?", (index_code,))
        if not row or not row["u"]:
            return None
        return datetime.fromisoformat(row["u"])

    # ---- calendar ----
    def load_calendar(self, start: date | None = None, end: date | None = None) -> list[date]:
        sql = "SELECT trade_date FROM trading_calendar WHERE is_open=1"
        params: list = []
        if start:
            sql += " AND trade_date>=?"
            params.append(start.isoformat())
        if end:
            sql += " AND trade_date<=?"
            params.append(end.isoformat())
        return [date.fromisoformat(r["trade_date"]) for r in self.db.query(sql, tuple(params))]

    def save_calendar(self, dates: list[date]) -> None:
        self.db.executemany(
            "INSERT INTO trading_calendar(trade_date,is_open) VALUES(?,1) "
            "ON CONFLICT(trade_date) DO UPDATE SET is_open=1",
            [(d.isoformat(),) for d in dates],
        )

    # ---- 数据源统计 ----
    def list_source_stats(self) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM data_source_stat ORDER BY priority")]

    def get_source_stat(self, name: str) -> dict | None:
        row = self.db.query_one("SELECT * FROM data_source_stat WHERE name=?", (name,))
        return dict(row) if row else None

    def upsert_source_stat(self, name: str, enabled: bool, priority: int, qps: float,
                           daily_quota: int, secret_ref: str = ""):
        self.db.execute(
            """INSERT INTO data_source_stat(name,enabled,priority,secret_ref,qps,daily_quota)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET enabled=excluded.enabled,
                 priority=excluded.priority, qps=excluded.qps,
                 daily_quota=excluded.daily_quota, secret_ref=excluded.secret_ref""",
            (name, int(enabled), priority, secret_ref, qps, daily_quota),
        )

    def record_call(self, name: str, ok: bool, latency_ms: float, today: str):
        stat = self.get_source_stat(name)
        if not stat:
            return
        used = stat["used_today"] + 1 if stat["stat_date"] == today else 1
        total, okc = stat["total_calls"] + 1, stat["ok_calls"] + (1 if ok else 0)
        fail = 0 if ok else stat["fail_count"] + 1
        state = "closed" if ok else stat["state"]
        avg = stat["avg_latency_ms"] or 0.0
        avg_latency = (avg * (total - 1) + latency_ms) / total
        self.db.execute(
            """UPDATE data_source_stat SET used_today=?,stat_date=?,total_calls=?,
               ok_calls=?,fail_count=?,state=?,avg_latency_ms=? WHERE name=?""",
            (used, today, total, okc, fail, state, avg_latency, name),
        )

    def set_breaker_state(self, name: str, state: str, fail_count: int):
        self.db.execute(
            "UPDATE data_source_stat SET state=?,fail_count=? WHERE name=?",
            (state, fail_count, name),
        )
