from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from webui import app_instance
from webui.models import AdminCreateUserIn, AdminUpdateUserIn, AuthIn

router = APIRouter()


# ---------- 鉴权辅助 ----------
def get_current_user(request: Request) -> dict:
    """从 Authorization: Bearer <token> 解析当前用户；无效则 401。"""
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    user = app_instance.APP.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求当前用户是管理员，否则 403。所有 /api/admin/* 用它（后端强制，非靠前端隐藏）。"""
    if (user or {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ---------- 登录 ----------
@router.post("/api/auth/login")
def auth_login(body: AuthIn) -> dict:
    try:
        return app_instance.APP.login(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/auth/me")
def auth_me(user: dict = Depends(get_current_user)) -> dict:
    return {"user": user}


# ---------- 用户管理（仅 admin）----------
@router.get("/api/admin/users")
def admin_users_list(user: dict = Depends(require_admin)) -> dict:
    return app_instance.APP.admin_list_users()


@router.post("/api/admin/users")
def admin_users_create(body: AdminCreateUserIn, user: dict = Depends(require_admin)) -> dict:
    try:
        return app_instance.APP.admin_create_user(body.username, body.password, body.max_stores)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/api/admin/users/{user_id}")
def admin_users_update(user_id: int, body: AdminUpdateUserIn,
                       user: dict = Depends(require_admin)) -> dict:
    try:
        return app_instance.APP.admin_update_user(user, user_id, body.max_stores, body.status, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/api/admin/users/{user_id}")
def admin_users_delete(user_id: int, user: dict = Depends(require_admin)) -> dict:
    try:
        return app_instance.APP.admin_delete_user(user, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------- 钱包 ----------
@router.get("/api/wallet")
def wallet_get(user: dict = Depends(get_current_user)) -> dict:
    return app_instance.APP.wallet_state()


@router.post("/api/wallet/recharge")
def wallet_recharge(body: dict, user: dict = Depends(get_current_user)) -> dict:
    try:
        return app_instance.APP.wallet_recharge(body.get("amount"), body.get("remark") or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------- 媒体预签名（插件直传 OSS）----------
@router.post("/api/media/presign")
def media_presign(body: dict, user: dict = Depends(get_current_user)) -> dict:
    try:
        return app_instance.APP.presign_media(body.get("items") or [])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
