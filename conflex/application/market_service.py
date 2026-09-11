"""行情应用服务：引导、股票池解析、按需增量拉取、缓存浏览（SDD 5.6）。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable


class MarketService:
    # 指数成分股本地缓存有效期（天），过期后下次使用时自动刷新
    INDEX_MEMBER_TTL_DAYS = 7

    def __init__(self, proxy, repo, job_manager=None):
        self.proxy = proxy
        self.repo = repo
        self.jobs = job_manager

    # ---- 股票池解析 ----
    def resolve_symbols(self, universe: str | None = None) -> list[str]:
        """把股票池名称解析为股票代码列表。

        板块池（all/main/chinext/star）直接查 instrument 表；
        指数池（sz50/hs300/zz500/zz1000）读 index_member 缓存，
        缓存不存在或超过 TTL 时自动从数据源拉取并落库。
        """
        name = universe or "all"
        index_code = self.repo.INDEX_POOL_CODES.get(name)
        if not index_code:
            return self.repo.resolve_universe(name)
        updated = self.repo.index_member_updated_at(index_code)
        if updated is None or datetime.now() - updated > timedelta(
                days=self.INDEX_MEMBER_TTL_DAYS):
            members = self.proxy.fetch_index_members(index_code)
            self.repo.replace_index_members(
                index_code, members, datetime.now().isoformat(timespec="seconds"))
        return self.repo.resolve_universe(name)

    # ---- 按需增量拉取（缓存优先）----
    def ensure_daily(self, symbols: list[str], start: date, end: date,
                     on_progress: Callable[[int, int, str], None] | None = None,
                     is_cancelled: Callable[[], bool] | None = None) -> dict:
        """确保 symbols 在 [start, end] 的行情已在本地缓存。

        逐票走 MarketDataProxy.get_daily（cache-first + next_gap 增量），
        单票失败不中断；返回 {"ok": n, "failed": [(symbol, reason), ...]}。
        """
        ok, failed = 0, []
        total = len(symbols)
        for i, sym in enumerate(symbols):
            if is_cancelled and is_cancelled():
                break
            try:
                self.proxy.get_daily(sym, start, end)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                failed.append((sym, str(exc)))
            if on_progress and ((i + 1) % 10 == 0 or i + 1 == total):
                on_progress(i + 1, total, sym)
        return {"ok": ok, "failed": failed}

    # ---- 同步基础操作 ----
    def bootstrap(self, years: int = 8) -> str:
        end = date.today()
        return self.proxy.bootstrap(end - timedelta(days=365 * years), end)

    def listed_symbols(self, day: date | None = None) -> list[str]:
        syms = self.repo.listed_symbols(day)
        return syms or self.repo.symbols_on_disk()

    # ---- 异步任务 ----
    def submit_update(self, symbols: list[str] | None = None,
                      start: date | None = None, end: date | None = None,
                      created_by: int | None = None, universe: str | None = None) -> int:
        params = {"symbols": symbols, "universe": universe,
                  "start": str(start) if start else None,
                  "end": str(end) if end else None}
        return self.jobs.submit("data_update", params,
                                lambda ctx: self._run(ctx, symbols, start, end, universe),
                                created_by)

    def submit_repair(self, symbol: str, start: date, end: date,
                      created_by: int | None = None) -> int:
        params = {"symbol": symbol, "start": str(start), "end": str(end)}
        return self.jobs.submit("data_repair", params,
                                lambda ctx: self._repair(ctx, symbol, start, end), created_by)

    def _run(self, ctx, symbols, start, end, universe=None) -> dict:
        if not self.repo.load_instruments():
            ctx.log("证券列表为空，先执行数据源引导…")
            self.bootstrap()
        if symbols:
            pass
        elif universe and universe != "all":
            symbols = self.repo.resolve_universe(universe)
            ctx.log(f"股票池 [{self.repo.UNIVERSES.get(universe, universe)}]：{len(symbols)} 只")
        else:
            symbols = self.listed_symbols()
        ctx.log(f"待更新股票 {len(symbols)} 只")

        def cb(done, total, sym):
            ctx.report_progress(done / total, f"更新中 {sym} ({done}/{total})")
            if done % 50 == 0:
                ctx.log(f"已完成 {done}/{total}")
            return not ctx.cancelled

        result = self.proxy.update_daily(symbols, start, end, cb)
        ctx.log(f"完成：成功 {result['ok']}，失败 {len(result['failed'])}")
        return result

    def _repair(self, ctx, symbol, start, end) -> dict:
        ctx.report_progress(0.1, f"强制重拉 {symbol}")
        df = self.proxy.fetch_with_failover(symbol, start, end, "none")
        self.repo.upsert(symbol, df, is_final=True, source="repair")
        ctx.report_progress(1.0, "修复完成")
        return {"symbol": symbol, "rows": len(df)}

    # ---- 查询 ----
    def coverage(self) -> list[dict]:
        return self.repo.coverage_rows()

    def bars(self, symbol: str, start, end, adjust="none"):
        return self.repo.read(symbol, start, end, adjust)

    def source_stats(self) -> list[dict]:
        return self.repo.list_source_stats()

    def storage_bytes(self) -> int:
        return self.repo.storage_bytes()
