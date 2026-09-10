"""FastAPI 依赖注入：容器获取与 JWT 鉴权（SDD 9.2）。"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, Request, status

from conflex.infra.security import decode_token


def get_container(request: Request):
    return request.app.state.container


def _token_from(header_value: str | None, token_query: str | None) -> str | None:
    if header_value and header_value.lower().startswith("bearer "):
        return header_value[7:]
    return token_query  # EventSource 无法自定义头，允许 query 传 token


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    jwt = _token_from(authorization, token)
    if not jwt:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少认证 Token")
    try:
        payload = decode_token(request.app.state.container.settings.jwt_secret(), jwt)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = request.app.state.container.system_repo.get_user(int(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return user


def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user
