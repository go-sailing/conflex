"""ASGI 入口：从环境/默认配置构建容器与应用。

启动：uvicorn conflex.entrypoints.webapi.asgi:app --host 127.0.0.1 --port 8899
"""
from __future__ import annotations

from conflex.config import load_settings
from conflex.container import Container
from conflex.entrypoints.webapi.app import create_app

_settings = load_settings()
container = Container(_settings)
app = create_app(container)
