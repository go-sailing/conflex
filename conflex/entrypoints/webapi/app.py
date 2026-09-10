"""FastAPI 应用工厂（SDD 9.1）。"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from conflex.errors import ConflexError
from conflex.entrypoints.webapi.routers import (
    auth, backtest, market, research, system, trade,
)


def create_app(container) -> FastAPI:
    app = FastAPI(title="Conflex Web API", version="0.1.0")
    app.state.container = container

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        request.state.trace_id = uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Trace-Id"] = request.state.trace_id
        return response

    @app.exception_handler(ConflexError)
    async def conflex_error_handler(request: Request, exc: ConflexError):
        return JSONResponse(
            status_code=getattr(exc, "http_status", 400),
            content={"code": exc.code, "msg": str(exc),
                     "trace_id": getattr(request.state, "trace_id", "")},
        )

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "service": "conflex"}

    for r in (auth.router, market.router, research.router, trade.router,
              backtest.router, system.router):
        app.include_router(r, prefix="/api/v1")

    # 托管前端构建产物（若存在）
    dist = Path(__file__).resolve().parents[3] / "resources" / "web_dist"
    if dist.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")

    return app
