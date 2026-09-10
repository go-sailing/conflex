"""因子研究与策略管理路由。"""
from __future__ import annotations

from datetime import date, datetime

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
    symbols: list[str] | None = None


@router.post("/factors/analysis")
def run_analysis(body: AnalysisIn, container=Depends(get_container),
                 user=Depends(require_admin)):
    params = body.model_dump()

    def job(ctx):
        ctx.report_progress(0.1, "加载行情面板")
        symbols = body.symbols or container.market_service.listed_symbols()
        end = datetime.strptime(body.end or date.today().isoformat(), "%Y-%m-%d").date()
        start = datetime.strptime(body.start, "%Y-%m-%d").date()
        panel = container.factor_service.load_panel(symbols, start, end)
        ctx.report_progress(0.5, f"分析因子 {body.factor}")
        return container.factor_service.analyze(
            body.factor, panel, body.horizon, body.groups)

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
