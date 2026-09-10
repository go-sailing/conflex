"""回测路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from conflex.entrypoints.webapi.deps import get_container, require_admin

router = APIRouter(tags=["backtest"])


class BacktestIn(BaseModel):
    name: str = "web-backtest"
    factors: list[dict]
    start: str
    end: str
    top_n: int = 20
    rebalance: str = "M"
    weighting: str = "equal"
    position_weighting: str = "equal"
    initial_cash: float = 1_000_000
    benchmark: str = ""
    adjust: str = "qfq"
    symbols: list[str] | None = None


@router.post("/backtests")
def create_backtest(body: BacktestIn, container=Depends(get_container),
                    user=Depends(require_admin)):
    job_id = container.backtest_service.submit(body.model_dump(), user["id"])
    return {"job_id": job_id}


@router.get("/backtests")
def list_backtests(container=Depends(get_container), user=Depends(require_admin)):
    return container.backtest_service.list_runs()


@router.get("/backtests/{run_id}/report")
def backtest_report(run_id: int, container=Depends(get_container),
                    user=Depends(require_admin)):
    run = container.backtest_service.get_run(run_id)
    if not run:
        raise HTTPException(404, "回测不存在")
    return run
