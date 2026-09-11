"""任务（含 SSE）、操作日志、隔离区、仪表盘路由。"""
from __future__ import annotations

import asyncio
import json
import queue
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from conflex.entrypoints.webapi.deps import get_container, get_current_user

router = APIRouter(tags=["system"])

_TERMINAL = {"succeeded", "failed", "cancelled"}


@router.get("/jobs")
def list_jobs(limit: int = 50, kind: str | None = None,
              container=Depends(get_container),
              user=Depends(get_current_user)):
    """列出异步任务。kind 参数可用于按类型过滤（如 data_update / factor_analysis / backtest）。"""
    return container.system_repo.list_jobs(limit, kind=kind)


@router.get("/jobs/{job_id}")
def get_job(job_id: int, container=Depends(get_container),
            user=Depends(get_current_user)):
    return container.jobs.get(job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, container=Depends(get_container),
               user=Depends(get_current_user)):
    container.jobs.cancel(job_id)
    return {"ok": True}


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: int, container=Depends(get_container),
                     user=Depends(get_current_user)):
    q = container.jobs.subscribe(job_id)

    async def event_gen():
        try:
            info = container.jobs.get(job_id)
            yield _sse("snapshot", _jsonable(info))
            if info["status"] in _TERMINAL:
                return
            while True:
                try:
                    event = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: q.get(timeout=15))
                except queue.Empty:
                    yield ": heartbeat\n\n"
                    continue
                yield _sse(event.get("type", "message"), event)
                if event.get("type") in ("finished", "error"):
                    break
        finally:
            container.jobs.unsubscribe(job_id, q)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _jsonable(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


@router.get("/operation-logs")
def operation_logs(limit: int = 100, container=Depends(get_container),
                   user=Depends(get_current_user)):
    return container.system_repo.list_logs(limit)


@router.get("/quarantine")
def quarantine(limit: int = 100, container=Depends(get_container),
               user=Depends(get_current_user)):
    return container.system_repo.list_quarantine(limit)


@router.get("/dashboard")
def dashboard(container=Depends(get_container), user=Depends(get_current_user)):
    cov = container.market_service.coverage()
    sources = container.market_service.source_stats()
    accounts = container.paper_service.list_accounts()
    jobs = container.system_repo.list_jobs(10)
    latest = max((r["end_date"] for r in cov), default=None)
    return {
        "symbol_count": len(cov),
        "latest_trade_date": latest,
        "storage_bytes": container.market_service.storage_bytes(),
        "sources": [{"name": s["name"], "enabled": s["enabled"], "state": s["state"],
                     "ok_calls": s["ok_calls"], "total_calls": s["total_calls"]}
                    for s in sources],
        "accounts": [{"id": a["id"], "name": a["name"],
                      "total_equity": round((a["cash_available"] + a["cash_frozen"]
                                             + (a["market_value"] or 0)), 2)}
                     for a in accounts],
        "recent_jobs": jobs,
    }
