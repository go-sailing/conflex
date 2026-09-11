"""多源行情代理：轮换、重试退避、熔断、限频、SingleFlight、缓存优先（SDD 5.2-5.5）。"""
from __future__ import annotations

import threading
import time
from datetime import date, timedelta

import pandas as pd

from conflex.domain.marketdata.quality import validate_daily
from conflex.errors import AllSourcesExhausted, QualityError, SourceError
from conflex.infra.datasources.breaker import CircuitBreaker
from conflex.infra.datasources.ratelimit import RateLimiter


class _SingleFlight:
    """相同参数并发请求合并，防缓存击穿。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._waiting: dict[str, threading.Event] = {}
        self._result: dict[str, object] = {}
        self._error: dict[str, Exception] = {}

    def run(self, key: str, fn, *args, **kwargs):
        with self._lock:
            if key in self._waiting:
                event = self._waiting[key]
                leader = False
            else:
                event = threading.Event()
                self._waiting[key] = event
                leader = True
        if not leader:
            event.wait()
            if key in self._error:
                raise self._error[key]
            return self._result[key]

        try:
            result = fn(*args, **kwargs)
            self._result[key] = result
            return result
        except Exception as exc:  # noqa: BLE001
            self._error[key] = exc
            raise
        finally:
            event.set()
            with self._lock:
                self._waiting.pop(key, None)
            # 结果短暂保留给同批等待者后清理
            self._result.pop(key, None)
            self._error.pop(key, None)


class MarketDataProxy:
    def __init__(self, sources, repo, system_repo=None,
                 max_retry: int = 2, fail_threshold: int = 5,
                 cooldown_seconds: int = 300, sleep=time.sleep):
        # sources: [(DataSourceCfg | None, adapter)] 二元组，priority 已排好
        self.sources = sources
        self.repo = repo
        self.system_repo = system_repo
        self.max_retry = max_retry
        self.breakers = {s.name: CircuitBreaker(fail_threshold, cooldown_seconds)
                         for _, s in sources}
        self.limiters = {}
        self.sleep = sleep
        self._inflight = _SingleFlight()

    def _limiter(self, cfg, source):
        key = source.name
        if key not in self.limiters:
            qps = getattr(cfg, "qps", 0.0) or 0.0
            quota = getattr(cfg, "daily_quota", 0) or 0
            self.limiters[key] = RateLimiter(qps, quota)
        return self.limiters[key]

    # ---- 对外主入口：缓存优先 ----
    def get_daily(self, symbol: str, start: date, end: date,
                  adjust: str = "none") -> pd.DataFrame:
        gap = self.repo.next_gap(symbol, start, end)
        if gap:
            self._inflight.run(
                f"bars:{symbol}:{gap[0]}:{gap[1]}:{adjust}",
                self._update_one, symbol, gap[0], gap[1], adjust)
        return self.repo.read(symbol, start, end, adjust)

    def _update_one(self, symbol: str, start: date, end: date, adjust: str):
        raw = self.fetch_with_failover(symbol, start, end, "none")  # 只缓存原始价
        errors, warnings = validate_daily(raw)
        if errors:
            if self.system_repo:
                self.system_repo.add_quarantine(symbol, "", "error", "; ".join(errors))
            raise QualityError(errors)
        is_final_mask = raw["trade_date"].dt.date < date.today()
        # 同批数据统一落盘：历史日期封闭
        self.repo.upsert(symbol, raw[is_final_mask], is_final=True, source="")
        if (~is_final_mask).any():
            self.repo.upsert(symbol, raw[~is_final_mask], is_final=False, source="")
        # 复权因子（若源支持）
        try:
            for _, src in self.sources:
                factors = src.fetch_adjust_factors(symbol, start, end)
                if factors:
                    adj_df = pd.DataFrame(
                        {"trade_date": [f.trade_date for f in factors],
                         "factor": [f.factor for f in factors]})
                    self.repo.upsert_adjust(symbol, adj_df)
                    break
        except Exception:  # noqa: BLE001 复权因子失败不阻断主流程
            pass

    def fetch_with_failover(self, symbol: str, start: date, end: date,
                            adjust: str = "none") -> pd.DataFrame:
        attempts: list[tuple[str, str]] = []
        today = date.today().isoformat()
        for cfg, src in self.sources:
            if cfg is not None and not getattr(cfg, "enabled", True):
                continue
            breaker = self.breakers[src.name]
            if not breaker.allow():
                attempts.append((src.name, "熔断中，跳过"))
                continue
            limiter = self._limiter(cfg, src)
            if limiter.quota_exhausted(today):
                attempts.append((src.name, "日配额耗尽"))
                continue
            for attempt in range(self.max_retry + 1):
                try:
                    limiter.acquire(today)
                    t0 = time.monotonic()
                    df = src.fetch_daily_bars(symbol, start, end, adjust)
                    latency = (time.monotonic() - t0) * 1000
                    breaker.record_success()
                    self._record(src.name, True, latency, today)
                    return df
                except SourceError as exc:
                    attempts.append((src.name, f"{exc.kind}: {exc}"))
                    self._record(src.name, False, 0, today)
                    if not exc.retriable or attempt == self.max_retry:
                        breaker.record_failure()
                        break
                    self.sleep(2 ** attempt)  # 1s/2s/4s 指数退避
                    breaker.record_failure()
                except Exception as exc:  # noqa: BLE001 未归类异常也容错换源
                    attempts.append((src.name, str(exc)))
                    breaker.record_failure()
                    break
        raise AllSourcesExhausted(attempts)

    def _record(self, name: str, ok: bool, latency: float, today: str):
        if self.repo and hasattr(self.repo, "record_call"):
            self.repo.record_call(name, ok, latency, today)

    # ---- 指数成分股（按需拉取，结果由仓储层缓存）----
    def fetch_index_members(self, index_code: str) -> list[tuple[str, str]]:
        """跨源拉取指数成分股 [(symbol, name)]，首个成功源即返回。"""
        attempts: list[tuple[str, str]] = []
        for cfg, src in self.sources:
            if cfg is not None and not getattr(cfg, "enabled", True):
                continue
            if not self.breakers[src.name].allow():
                attempts.append((src.name, "熔断中，跳过"))
                continue
            try:
                members = src.fetch_index_members(index_code)
                if members:
                    self.breakers[src.name].record_success()
                    return members
                attempts.append((src.name, "不支持或返回空"))
            except Exception as exc:  # noqa: BLE001
                attempts.append((src.name, str(exc)))
                self.breakers[src.name].record_failure()
        raise AllSourcesExhausted(attempts)

    # ---- 基础数据引导 ----
    def bootstrap(self, start: date | None = None, end: date | None = None) -> str:
        """从首个可用源拉取证券列表与交易日历，返回命中源。"""
        end = end or date.today()
        start = start or (end - timedelta(days=365 * 8))
        instruments, calendar, hit = [], None, ""
        for cfg, src in self.sources:
            if cfg is not None and not getattr(cfg, "enabled", True):
                continue
            try:
                instruments = src.fetch_instruments()
                calendar = src.fetch_calendar(start, end)
                if instruments and calendar:
                    hit = src.name
                    break
            except Exception:  # noqa: BLE001
                continue
        if not instruments:
            raise AllSourcesExhausted([(s.name, "引导失败") for _, s in self.sources])
        self.repo.save_instruments(instruments)
        self.repo.save_calendar(calendar)
        return hit

    def update_daily(self, symbols: list[str], start: date | None = None,
                     end: date | None = None, progress_cb=None) -> dict:
        """批量增量更新；单票失败不中断，返回统计。"""
        end = end or date.today()
        ok, failed = 0, []
        for i, sym in enumerate(symbols):
            try:
                gap = self.repo.next_gap(sym, start, end)
                if gap:
                    self._update_one(sym, gap[0], gap[1], "none")
                ok += 1
            except Exception as exc:  # noqa: BLE001
                failed.append((sym, str(exc)))
            if progress_cb:
                progress_cb(i + 1, len(symbols), sym)
        return {"total": len(symbols), "ok": ok, "failed": failed}
