"""因子研究与策略管理路由。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from conflex.entrypoints.webapi.deps import get_container, require_admin

router = APIRouter(tags=["research"])


@router.get("/factors")
def list_factors(container=Depends(get_container), user=Depends(require_admin)):
    return container.factor_service.list_factors()


class AnalysisIn(BaseModel):
    factor: str
    start: str
    end: str | None = None
    horizon: int = 5
    groups: int = 10
    universe: str = "all"
    symbols: list[str] | None = None


# 滚动窗口最长为 60 日（risk_vol_60），预留 120 个自然日 warmup，
# 保证分析起点当天的因子值有效；IC 统计再按 clip_start 截回用户区间
_WARMUP_DAYS = 120


@router.post("/factors/analysis")
def run_analysis(body: AnalysisIn, container=Depends(get_container),
                 user=Depends(require_admin)):
    params = body.model_dump()

    def job(ctx):
        # 1) 解析股票池（指数池成分缺失时自动拉取并缓存）
        ctx.report_progress(0.02, "解析股票池")
        if body.symbols:
            symbols = body.symbols
        else:
            symbols = container.market_service.resolve_symbols(body.universe)
        if not symbols:
            raise ValueError(f"股票池 {body.universe} 解析为空，请检查成分股数据是否可用")
        ctx.log(f"股票池 {body.universe}：{len(symbols)} 只股票")

        end = datetime.strptime(body.end or date.today().isoformat(), "%Y-%m-%d").date()
        start = datetime.strptime(body.start, "%Y-%m-%d").date()
        warm_start = start - timedelta(days=_WARMUP_DAYS)

        # 2) 按需增量拉取：缓存命中则跳过，缺口才请求数据源
        ctx.report_progress(0.05, f"检查行情缓存（{len(symbols)} 只）")

        def on_progress(done: int, total: int, sym: str):
            pct = 0.05 + 0.75 * done / max(total, 1)
            ctx.report_progress(pct, f"增量拉取行情 {done}/{total}（{sym}）")
            if done % 100 == 0:
                ctx.log(f"行情就绪 {done}/{total}")

        fetch_result = container.market_service.ensure_daily(
            symbols, warm_start, end,
            on_progress=on_progress, is_cancelled=lambda: ctx.cancelled)
        failed = fetch_result["failed"]
        ctx.log(f"行情检查完成：命中/成功 {fetch_result['ok']}，失败 {len(failed)}")
        if failed:
            ctx.log("失败样例：" + "; ".join(f"{s} {r[:40]}" for s, r in failed[:3]))

        # 3) 加载面板（含 warmup，保证滚动窗口因子在起点有效）
        ctx.report_progress(0.85, "加载行情面板")
        panel = container.factor_service.load_panel(symbols, warm_start, end)

        # 4) 因子分析（IC/分层只统计用户请求区间）
        ctx.report_progress(0.92, f"分析因子 {body.factor}")
        return container.factor_service.analyze(
            body.factor, panel, body.horizon, body.groups,
            clip_start=start, universe=body.universe,
            requested_count=len(symbols))

    job_id = container.jobs.submit("factor_analysis", params, job, user["id"])
    return {"job_id": job_id}


class ScoreIn(BaseModel):
    factors: list[str]
    date: str | None = None
    top_n: int = 20
    start: str | None = None
    weighting: str = "equal"


@router.get("/scores")
def scores(factors: str, date: str | None = None, top: int = 20,
           start: str | None = None, weighting: str = "equal",
           container=Depends(get_container), user=Depends(require_admin)):
    names = [f.strip() for f in factors.split(",") if f.strip()]
    symbols = container.market_service.listed_symbols()
    panel = container.factor_service.load_panel(symbols, start, date or None)
    board = container.selection_service.board(
        [{"name": n} for n in names], panel, on_date=date, top_n=top, weighting=weighting)
    return board.to_dict(orient="records")


# ---- 策略 CRUD ----
class StrategyIn(BaseModel):
    name: str
    factors: list[dict]
    weighting: str = "equal"
    rules: dict = {"top_n": 20}
    rebalance_freq: str = "M"


@router.get("/strategies")
def list_strategies(container=Depends(get_container), user=Depends(require_admin)):
    return container.trading_repo.list_strategies()


@router.post("/strategies")
def create_strategy(body: StrategyIn, container=Depends(get_container),
                    user=Depends(require_admin)):
    sid = container.trading_repo.save_strategy(
        body.name, body.factors, body.weighting, body.rules, body.rebalance_freq)
    return {"id": sid}


@router.put("/strategies/{sid}")
def update_strategy(sid: int, body: StrategyIn, container=Depends(get_container),
                    user=Depends(require_admin)):
    container.trading_repo.save_strategy(
        body.name, body.factors, body.weighting, body.rules, body.rebalance_freq, sid)
    return {"ok": True}


@router.delete("/strategies/{sid}")
def delete_strategy(sid: int, container=Depends(get_container),
                    user=Depends(require_admin)):
    container.trading_repo.delete_strategy(sid)
    return {"ok": True}
