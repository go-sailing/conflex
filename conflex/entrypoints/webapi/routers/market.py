"""行情数据：数据源管理、股票池、缓存浏览、K 线查询。"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from conflex.entrypoints.webapi.deps import get_container, require_admin

router = APIRouter(tags=["data"])


def _d(s: str | None):
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None


@router.get("/data-sources")
def list_sources(container=Depends(get_container), user=Depends(require_admin)):
    return container.market_service.source_stats()


@router.get("/universes")
def list_universes(container=Depends(get_container), user=Depends(require_admin)):
    return [{"key": k, "name": v} for k, v in container.market_repo.UNIVERSES.items()]


@router.post("/data-sources/{name}/test")
def test_source(name: str, container=Depends(get_container), user=Depends(require_admin)):
    hit = next(((cfg, src) for cfg, src in container.proxy.sources if src.name == name), None)
    if not hit:
        raise HTTPException(404, f"数据源 {name} 未启用或不存在")
    import time
    t0 = time.monotonic()
    ok = hit[1].health_check()
    return {"ok": ok, "latency_ms": int((time.monotonic() - t0) * 1000)}


@router.post("/data/bootstrap")
def bootstrap(container=Depends(get_container), user=Depends(require_admin)):
    hit = container.market_service.bootstrap()
    return {"source": hit, "symbols": len(container.market_repo.load_instruments())}


@router.get("/cache/coverage")
def coverage(page: int = 1, size: int = 50, keyword: str = "",
             container=Depends(get_container), user=Depends(require_admin)):
    rows, total = container.market_repo.coverage_rows_page(page, size, keyword)
    return {"rows": rows, "total": total,
            "storage_bytes": container.market_service.storage_bytes()}


@router.get("/market/instrument/{symbol:path}")
def instrument_info(symbol: str, container=Depends(get_container),
                    user=Depends(require_admin)):
    inst = container.market_repo.get_instrument(symbol)
    if not inst:
        raise HTTPException(404, "证券信息不存在")
    cov = container.market_repo.coverage(symbol)
    return {
        "symbol": inst.symbol, "name": inst.name, "exchange": inst.exchange,
        "board": inst.board, "is_st": inst.is_st,
        "list_date": inst.list_date.isoformat(),
        "delist_date": inst.delist_date.isoformat() if inst.delist_date else None,
        "cache_start": cov[0].isoformat() if cov else None,
        "cache_end": cov[1].isoformat() if cov else None,
    }


@router.get("/market/bars")
def bars(symbol: str, start: str | None = None, end: str | None = None,
         adjust: str = "qfq", container=Depends(get_container),
         user=Depends(require_admin)):
    df = container.market_service.bars(symbol, _d(start), _d(end), adjust)
    if df.empty:
        return []
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.strftime("%Y-%m-%d")
    # 逐列转 object 后再置空，避免 float 列上的 None 在 to_dict 时回退成 NaN；
    # numpy 标量（np.bool_/np.int64 等）统一 .item() 转为原生类型
    out = out.astype(object)
    records = out.where(pd.notna(out), None).to_dict(orient="records")
    for rec in records:
        for k, v in list(rec.items()):
            if isinstance(v, float) and pd.isna(v):
                rec[k] = None
            elif hasattr(v, "item"):
                rec[k] = v.item()
    return records
