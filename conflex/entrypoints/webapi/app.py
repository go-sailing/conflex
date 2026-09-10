"""FastAPI 应用工厂（SDD 9.1）。"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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

    # 托管前端构建产物（conflex/resources/web_dist）
    dist = Path(__file__).resolve().parents[2] / "resources" / "web_dist"
    index_file = dist / "index.html"
    if dist.exists() and index_file.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")

        @app.exception_handler(StarletteHTTPException)
        async def spa_fallback(request: Request, exc: StarletteHTTPException):
            # API 路径的 404 保持 JSON；其余 GET 请求回退到 SPA 入口（history 路由）
            if (
                exc.status_code == 404
                and request.method == "GET"
                and not request.url.path.startswith("/api/")
            ):
                return FileResponse(str(index_file))
            return JSONResponse(
                status_code=exc.status_code,
                content={"code": "not_found", "msg": exc.detail},
            )

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")

    return app
