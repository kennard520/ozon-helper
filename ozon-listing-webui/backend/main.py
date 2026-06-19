from __future__ import annotations

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app_service import FRONTEND_DIST, App
from backend.store import current_user_id
from backend.models import (
    AuthIn,
    AiImageBatchIn,
    AiImageIn,
    AiProposalPatchIn,
    AiVideoIn,
    BatchCollectIn,
    ExtCollectIn,
    ExtCollectParsedIn,
    ExtSnapshotIn,
    ImageCandidatesApplyIn,
    ImagePromptsIn,
    BatchUpdateDraftsIn,
    CollectIn,
    CollectKeywordIn,
    CommissionMapIn,
    DefaultWarehouseIn,
    FbsPullIn,
    OzonPullIn,
    ProcStateIn,
    PublishGroupIn,
    PublishIn,
    SettingsIn,
    ShipIn,
    AdminCreateUserIn,
    AdminUpdateUserIn,
)
from backend.media import media_file

app = FastAPI(title="Ozon 运营助理")
# 只放行浏览器插件来源（chrome-extension://...），不放行任何网站 → 恶意网页连不上本机后端。
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
APP = App()


# 纯 ASGI 中间件：从 Authorization Bearer 解出 user_id 存进 ContextVar，本请求内 store 全部按此用户隔离。
# 用纯 ASGI（非 BaseHTTPMiddleware）以保证 contextvar 能传到线程池里的同步路由。无 token → 默认 user 1(admin)。
class _UserContextMiddleware:
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.asgi_app(scope, receive, send)
            return
        token = ""
        for k, v in scope.get("headers") or []:
            if k == b"authorization":
                val = v.decode("latin-1")
                if val.lower().startswith("bearer "):
                    token = val[7:].strip()
                break
        user = APP.user_from_token(token) if token else None
        ctx = current_user_id.set(user["id"] if user else 1)
        try:
            await self.asgi_app(scope, receive, send)
        finally:
            current_user_id.reset(ctx)


app.add_middleware(_UserContextMiddleware)


# ---------- 鉴权 ----------
def get_current_user(request: Request) -> dict:
    """从 Authorization: Bearer <token> 解析当前用户；无效则 401。"""
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    user = APP.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求当前用户是管理员，否则 403。所有 /api/admin/* 用它（后端强制，非靠前端隐藏）。"""
    if (user or {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


@app.post("/api/auth/login")
def auth_login(body: AuthIn) -> dict:
    try:
        return APP.login(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(get_current_user)) -> dict:
    return {"user": user}


# ---------- 用户管理（仅 admin）----------
@app.get("/api/admin/users")
def admin_users_list(user: dict = Depends(require_admin)) -> dict:
    return APP.admin_list_users()


@app.post("/api/admin/users")
def admin_users_create(body: AdminCreateUserIn, user: dict = Depends(require_admin)) -> dict:
    try:
        return APP.admin_create_user(body.username, body.password, body.max_stores)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.patch("/api/admin/users/{user_id}")
def admin_users_update(user_id: int, body: AdminUpdateUserIn,
                       user: dict = Depends(require_admin)) -> dict:
    try:
        return APP.admin_update_user(user, user_id, body.max_stores, body.status, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------- 钱包 ----------
@app.get("/api/wallet")
def wallet_get(user: dict = Depends(get_current_user)) -> dict:
    return APP.wallet_state()


@app.post("/api/wallet/recharge")
def wallet_recharge(body: dict, user: dict = Depends(get_current_user)) -> dict:
    try:
        return APP.wallet_recharge(body.get("amount"), body.get("remark") or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------- 媒体预签名（插件直传 OSS）----------
@app.post("/api/media/presign")
def media_presign(body: dict, user: dict = Depends(get_current_user)) -> dict:
    try:
        return APP.presign_media(body.get("items") or [])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/state")
def get_state() -> dict:
    return APP.state()


@app.get("/api/drafts")
def get_drafts(status: str = "all", page: int = 1, page_size: int = 20,
               store_client_id: str | None = None) -> dict:
    # 草稿绑定店：前端传当前店 → 只列该店草稿；不传(None)=不按店过滤（兼容）
    return APP.list_drafts(status=status, page=page, page_size=page_size, store_client_id=store_client_id)


@app.get("/api/category/search")
def category_search(q: str = "", limit: int = 500) -> dict:
    try:
        return APP.search_category(q, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/category/tree")
def category_tree() -> dict:
    try:
        return APP.category_tree()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/category/resolve")
def category_resolve(cat: int, type: int) -> dict:
    try:
        return APP.resolve_category(cat, type)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/category/attributes")
def category_attributes(cat: int, type: int, language: str = "ZH_HANS") -> dict:
    try:
        return APP.category_attributes(cat, type, language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/attribute/values/search")
def attribute_values_search(cat: int, type: int, attr: int, q: str = "", language: str = "ZH_HANS") -> dict:
    try:
        return APP.brand_search(cat, type, attr, q, language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/drafts/{draft_id}/required-check")
def required_check(draft_id: int, language: str = "ZH_HANS") -> dict:
    try:
        return APP.required_check(draft_id, language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/commission-map")
def get_commission_map(cat: int, type: int) -> dict:
    try:
        return APP.get_commission_map(cat, type)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


# 本地图片托管：/media/<key>/<file> → data/images/ 下的下载图（采集时落地的本地副本）
@app.get("/media/{path:path}")
def media(path: str) -> FileResponse:
    fpath = media_file(path)
    if fpath is None:
        raise HTTPException(status_code=404, detail="media not found")
    return FileResponse(fpath)


# 图片下载代理：服务器用 OSS「内网 endpoint」取图后吐给客户端，省 OSS 外网出流量
# （ECS 固定带宽包月，等于免费）。只代理 ozon-media/ 前缀（内容哈希命名）。
# 上传仍是插件预签名直传 OSS 外网，不走这里。
@app.get("/oss/{key:path}")
def oss_proxy(key: str) -> Response:
    if not key.startswith("ozon-media/"):
        raise HTTPException(status_code=404, detail="not found")
    from backend.oss import OssClient  # noqa: PLC0415
    oss = OssClient(APP.store.get_settings())
    if not oss.configured():
        raise HTTPException(status_code=503, detail="OSS 未配置")
    try:
        data, ct = oss.get_object(key)
    except Exception:
        raise HTTPException(status_code=404, detail="对象不存在")
    return Response(
        content=data, media_type=ct,
        headers={"Cache-Control": "public, max-age=31536000"},
    )


# 前端入口：Vue 构建产物 frontend/dist/index.html。
# dist 是构建产物（.gitignore），首次运行前需 `cd frontend && npm run build`。
@app.get("/")
def index() -> FileResponse:
    dist_index = FRONTEND_DIST / "index.html"
    if not dist_index.exists():
        raise HTTPException(
            status_code=503,
            detail="前端未构建：请先在 frontend/ 下执行 `npm run build`",
        )
    return FileResponse(dist_index)


@app.post("/api/settings")
def save_settings(payload: SettingsIn) -> dict:
    try:
        return APP.save_settings(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# 服务器端采集已停用——采集全部由浏览器插件就地完成（推送 /api/ext/collect-parsed）。
# 旧路由 /api/drafts/collect、/api/drafts/collect-keyword、/api/batch-collect、/api/ext/collect 已移除。


@app.patch("/api/drafts/{draft_id}")
async def update_draft(draft_id: int, request: Request) -> dict:
    body = await request.json()
    try:
        return APP.update_draft(draft_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/batch-update")
def batch_update_drafts(body: BatchUpdateDraftsIn) -> dict:
    patch = body.model_dump(exclude_none=True)
    ids = patch.pop("ids", [])
    try:
        return APP.batch_update_drafts(ids, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/batch-publish")
def batch_publish(body: dict) -> dict:
    ids = body.get("ids") or []
    return APP.batch_publish(ids, body.get("store_client_id"))


@app.post("/api/drafts/{draft_id}/copy-to-store")
def copy_draft_to_store(draft_id: int, body: dict) -> dict:
    try:
        return APP.copy_draft_to_store(draft_id, body.get("store_client_id"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/drafts/{draft_id}/publish-preview")
def publish_preview(draft_id: int, store_client_id: str | None = None) -> dict:
    try:
        return APP.publish_preview(draft_id, store_client_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/drafts/{draft_id}/publish")
def publish(draft_id: int, body: PublishIn | None = None) -> dict:
    try:
        scid = body.store_client_id if body else None
        return APP.publish(draft_id, scid)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/translate")
def translate_draft(draft_id: int) -> dict:
    try:
        return APP.translate_draft(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/auto-map")
def auto_map(draft_id: int) -> dict:
    try:
        return APP.auto_map_attributes(draft_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/ai-generate")
def ai_generate(draft_id: int) -> dict:
    try:
        return APP.ai_generate(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/ai-image-prompts")
def ai_image_prompts(draft_id: int, body: ImagePromptsIn) -> dict:
    try:
        return APP.ai_image_prompts(draft_id, body.n_points)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/ai-image")
def ai_image(draft_id: int, body: AiImageIn) -> dict:
    try:
        return APP.ai_generate_image(draft_id, mode=body.mode, prompt=body.prompt,
                                     source_url=body.source_url, size=body.size,
                                     as_main=bool(body.as_main))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/ai-video")
def ai_video_start(draft_id: int, body: AiVideoIn) -> dict:
    try:
        return APP.start_ai_video(draft_id, prompt=body.prompt, image_url=body.image_url)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/ai-video/status")
def ai_video_status_route() -> dict:
    return APP.ai_video_status()


@app.post("/api/ai-video/stop")
def ai_video_stop_route() -> dict:
    return APP.stop_ai_video()


@app.patch("/api/drafts/{draft_id}/ai-proposal")
def patch_ai_proposal(draft_id: int, body: AiProposalPatchIn) -> dict:
    try:
        return APP.patch_ai_proposal(draft_id, body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/ai-proposal/apply")
def apply_ai_proposal(draft_id: int) -> dict:
    try:
        return APP.apply_ai_proposal(draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/drafts/{draft_id}")
def delete_draft(draft_id: int) -> dict:
    try:
        return APP.delete(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/commission-map")
def save_commission_map(payload: CommissionMapIn) -> dict:
    return APP.save_commission_map(payload.model_dump())


@app.post("/api/ozon/pull")
def ozon_pull(body: OzonPullIn) -> dict:
    try:
        return APP.pull_ozon_products(body.visibility)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))




@app.get("/api/warehouses")
def warehouses(store_client_id: str | None = None) -> dict:
    return APP.list_warehouses(store_client_id)


@app.post("/api/warehouses/sync")
def warehouses_sync(store_client_id: str | None = None) -> dict:
    try:
        return APP.sync_warehouses(store_client_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/warehouses/default")
def warehouses_default(body: DefaultWarehouseIn, store_client_id: str | None = None) -> dict:
    return APP.set_default_warehouse(body.warehouse_id, store_client_id)


# ---------- 功能⑤：FBS 备货发货 ----------
@app.post("/api/fbs/pull")
def fbs_pull(body: FbsPullIn, store_client_id: str | None = None) -> dict:
    try:
        return APP.pull_fbs(body.status, body.days, store_client_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/fbs/procurement")
def fbs_procurement(store_client_id: str | None = None) -> dict:
    return APP.list_procurement(store_client_id)


@app.post("/api/fbs/procurement/{pid}/state")
def fbs_proc_state(pid: int, body: ProcStateIn, store_client_id: str | None = None) -> dict:
    return APP.set_procurement_state(pid, body.purchase_state, body.note, store_client_id)


@app.post("/api/fbs/ship")
def fbs_ship(body: ShipIn, store_client_id: str | None = None) -> dict:
    try:
        return APP.ship_posting(body.posting_number, store_client_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/fbs/label")
def fbs_label(posting: str, store_client_id: str | None = None) -> Response:
    try:
        pdf = APP.fbs_label(posting, store_client_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{posting}.pdf"'})


@app.post("/api/drafts/{draft_id}/media")
async def upload_media(draft_id: int, file: UploadFile = File(...), kind: str = Form("image")) -> dict:
    from backend.media import save_upload  # noqa: PLC0415
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大(>20MB)")
    url = save_upload(f"draft-{draft_id}", file.filename or "upload", data)
    return {"url": url, "kind": kind}


# ---------- 插件桥接（/api/ext/*）----------
@app.get("/api/ext/ping")
def ext_ping() -> dict:
    return APP.ext_ping()


@app.post("/api/ext/snapshot")
def ext_snapshot(body: ExtSnapshotIn) -> dict:
    try:
        return APP.ext_add_snapshot(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/ext/snapshots")
def ext_snapshots(product_id: str) -> dict:
    return APP.ext_snapshots(product_id)


@app.post("/api/ext/collect-parsed")
def ext_collect_parsed(body: ExtCollectParsedIn) -> dict:
    try:
        return APP.ext_collect_parsed(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/ext/publish-group")
def ext_publish_group(body: PublishGroupIn) -> dict:
    try:
        return APP.publish_variant_group(body.variant_group, body.store_client_id, body.model_name)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# catch-all 静态挂载：托管 Vue 构建产物 frontend/dist。
# 必须放在所有 /api/* 与 /media/* 路由之后（优先级最低）。
# check_dir=False：dist 未构建时不在导入期报错，访问时由 index() 给出 503 提示。
app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True, check_dir=False), name="frontend")
