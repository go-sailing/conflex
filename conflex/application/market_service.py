"""行情应用服务：引导、增量更新、缓存浏览（SDD 5.6）。"""
from __future__ import annotations

from datetime import date, timedelta


class MarketService:
    def __init__(self, proxy, repo, job_manager=None):
        self.proxy = proxy
        self.repo = repo
        self.jobs = job_manager

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
                      created_by: int | None = None) -> int:
        params = {"symbols": symbols, "start": str(start) if start else None,
                  "end": str(end) if end else None}
        return self.jobs.submit("data_update", params,
                                lambda ctx: self._run(ctx, symbols, start, end), created_by)

    def submit_repair(self, symbol: str, start: date, end: date,
                      created_by: int | None = None) -> int:
        params = {"symbol": symbol, "start": str(start), "end": str(end)}
        return self.jobs.submit("data_repair", params,
                                lambda ctx: self._repair(ctx, symbol, start, end), created_by)

    def _run(self, ctx, symbols, start, end) -> dict:
        if not self.repo.load_instruments():
            ctx.log("证券列表为空，先执行数据源引导…")
            self.bootstrap()
        symbols = symbols or self.listed_symbols()
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
