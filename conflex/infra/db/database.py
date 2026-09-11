"""SQLite 连接、DDL 与轻量版本迁移（SDD 10）。"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migration (version INTEGER PRIMARY KEY);

CREATE TABLE IF NOT EXISTS instrument (
  symbol TEXT PRIMARY KEY, name TEXT NOT NULL, exchange TEXT NOT NULL,
  board TEXT, list_date TEXT NOT NULL, delist_date TEXT, is_st INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trading_calendar (
  trade_date TEXT PRIMARY KEY, is_open INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cache_meta (
  symbol TEXT NOT NULL, freq TEXT NOT NULL DEFAULT 'daily',
  start_date TEXT NOT NULL, end_date TEXT NOT NULL,
  is_final INTEGER NOT NULL DEFAULT 0, adj_type TEXT NOT NULL DEFAULT 'none',
  source TEXT, updated_at TEXT NOT NULL,
  PRIMARY KEY (symbol, freq, adj_type)
);

CREATE TABLE IF NOT EXISTS index_member (
  index_code TEXT NOT NULL, symbol TEXT NOT NULL,
  name TEXT, updated_at TEXT NOT NULL,
  PRIMARY KEY (index_code, symbol)
);

CREATE TABLE IF NOT EXISTS data_source_stat (
  name TEXT PRIMARY KEY, enabled INTEGER DEFAULT 1, priority INTEGER,
  secret_ref TEXT, qps REAL, daily_quota INTEGER,
  used_today INTEGER DEFAULT 0, stat_date TEXT,
  state TEXT DEFAULT 'closed', fail_count INTEGER DEFAULT 0,
  total_calls INTEGER DEFAULT 0, ok_calls INTEGER DEFAULT 0, avg_latency_ms REAL
);

CREATE TABLE IF NOT EXISTS factor_def (
  name TEXT PRIMARY KEY, category TEXT, description TEXT,
  deps_json TEXT, params_json TEXT, builtin INTEGER DEFAULT 1, enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS strategy (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  factors_json TEXT NOT NULL, weighting TEXT DEFAULT 'equal',
  rules_json TEXT NOT NULL, rebalance_freq TEXT DEFAULT 'M',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE, initial_cash REAL NOT NULL,
  cash_available REAL NOT NULL, cash_frozen REAL NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS position (
  account_id INTEGER NOT NULL, symbol TEXT NOT NULL,
  qty INTEGER NOT NULL, available_qty INTEGER NOT NULL,
  cost_price REAL NOT NULL, last_price REAL,
  PRIMARY KEY (account_id, symbol)
);

CREATE TABLE IF NOT EXISTS "order" (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL, symbol TEXT NOT NULL,
  side TEXT NOT NULL, order_type TEXT NOT NULL,
  qty INTEGER NOT NULL, filled_qty INTEGER DEFAULT 0,
  price REAL, avg_price REAL, status TEXT NOT NULL,
  signal_date TEXT, trade_date TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_order_account ON "order"(account_id, status);

CREATE TABLE IF NOT EXISTS trade (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL, account_id INTEGER NOT NULL,
  symbol TEXT NOT NULL, side TEXT NOT NULL,
  qty INTEGER NOT NULL, price REAL NOT NULL,
  commission REAL, stamp_tax REAL, transfer_fee REAL, trade_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_flow (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL, type TEXT NOT NULL,
  amount REAL NOT NULL, ref_order_id INTEGER,
  occur_date TEXT NOT NULL, balance_after REAL
);

CREATE TABLE IF NOT EXISTS account_snapshot (
  account_id INTEGER NOT NULL, trade_date TEXT NOT NULL,
  cash REAL, market_value REAL, total_equity REAL,
  PRIMARY KEY (account_id, trade_date)
);

CREATE TABLE IF NOT EXISTS backtest_run (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy_id INTEGER, name TEXT, params_json TEXT NOT NULL,
  start_date TEXT, end_date TEXT, benchmark TEXT,
  data_version TEXT, code_version TEXT,
  status TEXT NOT NULL, metrics_json TEXT,
  created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS backtest_equity (
  run_id INTEGER NOT NULL, trade_date TEXT NOT NULL,
  equity REAL, benchmark REAL, drawdown REAL,
  PRIMARY KEY (run_id, trade_date)
);
CREATE TABLE IF NOT EXISTS backtest_trade (
  run_id INTEGER NOT NULL, trade_date TEXT, symbol TEXT,
  side TEXT, qty INTEGER, price REAL, fee REAL
);

CREATE TABLE IF NOT EXISTS job (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL, status TEXT NOT NULL,
  progress REAL DEFAULT 0, stage TEXT,
  params_json TEXT, result_json TEXT, error TEXT,
  logs_file TEXT, created_by INTEGER,
  created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
);

CREATE TABLE IF NOT EXISTS "user" (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  role TEXT DEFAULT 'admin',
  created_at TEXT NOT NULL, last_login_at TEXT,
  login_fail_count INTEGER DEFAULT 0, locked_until TEXT
);

CREATE TABLE IF NOT EXISTS operation_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER, action TEXT NOT NULL, target TEXT,
  detail_json TEXT, ip TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quarantine_record (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT, source TEXT, trade_date TEXT, level TEXT,
  reason TEXT, file_path TEXT, created_at TEXT NOT NULL
);
"""


class Database:
    """线程安全的 SQLite 封装：WAL + 写串行化。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.init_schema()

    def init_schema(self):
        with self._lock:
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()

    @property
    def lock(self):
        return self._lock

    def execute(self, sql: str, params: tuple | dict = ()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql: str, seq):
        with self._lock:
            cur = self._conn.executemany(sql, seq)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def close(self):
        with self._lock:
            self._conn.close()
