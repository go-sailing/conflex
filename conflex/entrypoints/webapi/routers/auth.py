"""认证：首次启动引导建管理员、登录、当前用户、改密。"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from conflex.entrypoints.webapi.deps import get_container, get_current_user
from conflex.infra.security import (
    create_access_token, hash_password, verify_password,
)

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/auth/login")
def login(body: LoginIn, request: Request, container=Depends(get_container)):
    repo = container.system_repo
    user = repo.get_user_by_name(body.username)
    # 首次启动：无任何用户时，用本次提交的凭据创建管理员
    if user is None and repo.user_count() == 0:
        uid = repo.create_user(body.username, hash_password(body.password), role="admin")
        user = repo.get_user(uid)
        repo.add_log(uid, "bootstrap_admin", body.username, ip=request.client.host)
    elif user is None or not verify_password(body.password, user["password_hash"]):
        if user:
            locked = (datetime.now() + timedelta(minutes=15)).isoformat(timespec="seconds")
            repo.touch_login(user["id"], locked if user["login_fail_count"] + 1 >= 5 else None, 1)
        raise HTTPException(401, "用户名或密码错误")

    locked_until = user.get("locked_until")
    if locked_until and locked_until > datetime.now().isoformat():
        raise HTTPException(423, "登录失败过多，账户已锁定 15 分钟")

    token = create_access_token(
        container.settings.jwt_secret(),
        {"sub": str(user["id"]), "username": user["username"], "role": user["role"]},
        ttl_hours=container.settings.jwt_expire_hours,
    )
    repo.touch_login(user["id"])
    repo.add_log(user["id"], "login", "", ip=request.client.host)
    return {"token": token, "role": user["role"],
            "expires_in": container.settings.jwt_expire_hours * 3600,
            "bootstrap": repo.user_count() == 1}


@router.get("/auth/me")
def me(user=Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


@router.put("/auth/password")
def change_password(body: PasswordIn, request: Request,
                    container=Depends(get_container), user=Depends(get_current_user)):
    if not verify_password(body.old_password, user["password_hash"]):
        raise HTTPException(400, "原密码错误")
    container.system_repo.update_password(user["id"], hash_password(body.new_password))
    container.system_repo.add_log(user["id"], "change_password", "", ip=request.client.host)
    return {"ok": True}
