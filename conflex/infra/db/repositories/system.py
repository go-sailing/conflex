"""用户 / 异步任务 / 操作日志 / 隔离区仓储。"""
from __future__ import annotations

import json
from datetime import datetime


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SystemRepository:
    def __init__(self, db):
        self.db = db

    # ---- 用户 ----
    def create_user(self, username: str, password_hash: str, role: str = "admin") -> int:
        cur = self.db.execute(
            "INSERT INTO \"user\"(username,password_hash,role,created_at) VALUES(?,?,?,?)",
            (username, password_hash, role, _now()))
        return cur.lastrowid

    def get_user_by_name(self, username: str) -> dict | None:
        r = self.db.query_one("SELECT * FROM \"user\" WHERE username=?", (username,))
        return dict(r) if r else None

    def get_user(self, user_id: int) -> dict | None:
        r = self.db.query_one("SELECT * FROM \"user\" WHERE id=?", (user_id,))
        return dict(r) if r else None

    def user_count(self) -> int:
        return self.db.query_one("SELECT COUNT(*) c FROM \"user\"")["c"]

    def update_password(self, user_id: int, password_hash: str):
        self.db.execute("UPDATE \"user\" SET password_hash=? WHERE id=?", (password_hash, user_id))

    def touch_login(self, user_id: int, locked_until: str | None = None, fail_delta: int = 0):
        self.db.execute(
            "UPDATE \"user\" SET last_login_at=?, login_fail_count=login_fail_count+?, locked_until=? WHERE id=?",
            (_now(), fail_delta, locked_until, user_id))

    # ---- 任务 ----
    def insert_job(self, kind: str, params: dict, created_by: int | None, logs_file: str) -> int:
        cur = self.db.execute(
            """INSERT INTO job(kind,status,progress,stage,params_json,logs_file,created_by,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (kind, "queued", 0.0, "queued", json.dumps(params, ensure_ascii=False),
             logs_file, created_by, _now()))
        return cur.lastrowid

    def update_job(self, job_id: int, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [job_id]
        self.db.execute(f"UPDATE job SET {cols} WHERE id=?", tuple(vals))

    def get_job(self, job_id: int) -> dict | None:
        r = self.db.query_one("SELECT * FROM job WHERE id=?", (job_id,))
        if not r:
            return None
        d = dict(r)
        d["params"] = json.loads(r["params_json"]) if r["params_json"] else {}
        d["result"] = json.loads(r["result_json"]) if r["result_json"] else None
        return d

    def list_jobs(self, limit: int = 50) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT id,kind,status,progress,stage,error,created_at,started_at,finished_at "
            "FROM job ORDER BY id DESC LIMIT ?", (limit,))]

    # ---- 操作日志 ----
    def add_log(self, user_id: int | None, action: str, target: str = "",
                detail: dict | None = None, ip: str = ""):
        self.db.execute(
            """INSERT INTO operation_log(user_id,action,target,detail_json,ip,created_at)
               VALUES(?,?,?,?,?,?)""",
            (user_id, action, target,
             json.dumps(detail or {}, ensure_ascii=False), ip, _now()))

    def list_logs(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM operation_log ORDER BY id DESC LIMIT ?", (limit,))]

    # ---- 隔离区 ----
    def add_quarantine(self, symbol: str, source: str, level: str, reason: str,
                       file_path: str = ""):
        self.db.execute(
            """INSERT INTO quarantine_record(symbol,source,trade_date,level,reason,file_path,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (symbol, source, "", level, reason, file_path, _now()))

    def list_quarantine(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM quarantine_record ORDER BY id DESC LIMIT ?", (limit,))]
