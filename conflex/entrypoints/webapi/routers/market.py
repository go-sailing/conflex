"""行情数据：数据源管理、更新任务、缓存浏览、K 线查询。"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from conflex.entrypoints.webapi.deps import get_container, require_admin

router = APIRouter(tags=["data"])


class UpdateIn(BaseModel):
    type: str = "update"           # update / repair
    symbols: list[str] | None = None
    symbol: str | None = None
    start: str | None = None
    end: str | None = None


def _d(s: str | None):
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None


@router.get("/data-sources")
def list_sources(container=Depends(get_container), user=Depends(require_admin)):
    return container.market_service.source_stats()


@router.post("/data-sources/{name}/test")
def test_source(name: str, container=Depends(get_container), user=Depends(require_admin)):
    hit = next(((cfg, src) for cfg, src in container.proxy.sources if src.name == name), None)
    if not hit:
        raise HTTPException(404, f"数据源 {name} 未启用或不存在")
    import time
    t0 = time.monotonic()
    ok = hit[1].health_check()
    return {"ok": ok, "latency_ms": int((time.monotonic() - t0) * 1000)}


@router.post("/data/jobs")
def create_data_job(body: UpdateIn, request: Request, container=Depends(get_container),
                    user=Depends(require_admin)):
    if body.type == "repair":
        if not body.symbol or not body.start:
            raise HTTPException(400, "repair 需要 symbol 与 start")
        job_id = container.market_service.submit_repair(
            body.symbol, _d(body.start), _d(body.end) or date.today(), user["id"])
    else:
        job_id = container.market_service.submit_update(
            body.symbols, _d(body.start), _d(body.end), user["id"])
    container.system_repo.add_log(user["id"], f"data_{body.type}", body.symbol or "ALL",
                                  body.model_dump(), request.client.host)
    return {"job_id": job_id}


@router.post("/data/bootstrap")
def bootstrap(container=Depends(get_container), user=Depends(require_admin)):
    hit = container.market_service.bootstrap()
    return {"source": hit, "symbols": len(container.market_repo.load_instruments())}


@router.get("/cache/coverage")
def coverage(container=Depends(get_container), user=Depends(require_admin)):
    return {"rows": container.market_service.coverage(),
            "storage_bytes": container.market_service.storage_bytes()}


@router.get("/market/bars")
def bars(symbol: str, start: str | None = None, end: str | None = None,
         adjust: str = "qfq", container=Depends(get_container),
         user=Depends(require_admin)):
    df = container.market_service.bars(symbol, _d(start), _d(end), adjust)
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.strftime("%Y-%m-%d")
    return out.where(out.notna(), None).to_dict(orient="records")
