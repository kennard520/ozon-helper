from __future__ import annotations

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from webui.app_service import FRONTEND_DIST, App
from webui.media import media_file
from webui.models import (
    AiImageBatchIn,
    AiImageIn,
    AiProposalPatchIn,
    AiVideoIn,
    BatchCollectIn,
    CommissionMapIn,
    DefaultWarehouseIn,
    ExtCollectIn,
    ExtCollectParsedIn,
    ExtSnapshotIn,
    FbsPullIn,
    ImageCandidatesApplyIn,
    ImagePromptsIn,
    OzonPullIn,
    ProcStateIn,
    PublishGroupIn,
    PublishIn,
    ShipIn,
)
from webui.store import current_user_id

app = FastAPI(title="Ozon 运营助理")
# 只放行浏览器插件来源（chrome-extension://...），不放行任何网站 → 恶意网页连不上本机后端。
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
APP = App()
# 把单例写入 app_instance，供 routers 直接 import 而无需经过 main（避免循环）
import webui.app_instance as _ai_mod  # noqa: E402
_ai_mod.APP = APP
from webui.routers import auth as auth_router, settings as settings_router, category as category_router, drafts as drafts_router  # noqa: E402
app.include_router(auth_router.router)
app.include_router(settings_router.router)
app.include_router(category_router.router)
app.include_router(drafts_router.router)


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


# 请求级 scoped-session 用的全局 sessionmaker 已在 App() → Store.init() 里 bind_engine 绑好
# （与本进程的 Store 同一个库）；这里只需 session_scope 包请求即可。
from ozon_common.dal.session import session_scope  # noqa: E402


# 请求级 scoped-session：进入请求开 session 绑 ContextVar，结束提交/回滚/关闭。
# async 中间件设的 ContextVar 会被 anyio 复制进同步端点的线程池（已实测）。
@app.middleware("http")
async def _db_session_mw(request: Request, call_next):
    with session_scope():
        return await call_next(request)


@app.get("/api/commission-map")
def get_commission_map(cat: int, type: int) -> dict:
    try:
        return APP.get_commission_map(cat, type)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


# realFBS 运费路线表（智能定价用）：可导出 CSV → Excel 维护 → 导入覆盖
@app.get("/api/realfbs-routes")
def get_realfbs_routes() -> dict:
    return APP.realfbs_routes()


@app.get("/api/realfbs-routes/export")
def export_realfbs_routes() -> Response:
    csv_text = APP.export_realfbs_routes_csv()
    return Response(
        content=csv_text, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=realfbs_routes.csv"},
    )


@app.post("/api/realfbs-routes/import")
async def import_realfbs_routes(request: Request) -> dict:
    body = await request.json()
    try:
        return APP.import_realfbs_routes(str((body or {}).get("csv") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# realFBS 佣金类目表（智能定价用，只 FBS=RFBS）：导出 xlsx → Excel 维护 → 导入覆盖；
# 也可直接丢 Ozon 官方 Tarifs xlsx 导入（自动认 'MP Tree Tarifs CN' sheet 的 RFBS 三档）
@app.get("/api/commission-categories")
def get_commission_categories() -> dict:
    return APP.commission_categories()


@app.get("/api/commission-categories/export")
def export_commission_categories() -> Response:
    data = APP.export_commission_categories_xlsx()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=commission_categories.xlsx"},
    )


@app.post("/api/commission-categories/import")
async def import_commission_categories(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    try:
        return APP.import_commission_categories_xlsx(data)
    except ValueError as exc:
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
    from ozon_common.oss import OssClient  # noqa: PLC0415
    from webui.media import read_media_bytes  # noqa: PLC0415
    oss = OssClient(APP.store.get_settings(), local_reader=read_media_bytes)
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


# 服务器端采集已停用——采集全部由浏览器插件就地完成（推送 /api/ext/collect-parsed）。
# 旧路由 /api/drafts/collect、/api/drafts/collect-keyword、/api/batch-collect、/api/ext/collect 已移除。


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


@app.get("/api/drafts/{draft_id}/publish-preflight")
def publish_preflight(draft_id: int) -> dict:
    """发布前核对清单(硬拦/建议/待核对/已就绪)。"""
    try:
        return APP.publish_preflight(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


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


@app.post("/api/drafts/{draft_id}/recognize-category")
def recognize_category(draft_id: int) -> dict:
    """AI 识别类别(类别识别)，写入草稿。特征值识别(auto-map)的前置。"""
    try:
        return APP.recognize_category(draft_id)
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


@app.post("/api/drafts/{draft_id}/ai-fill-attributes")
def ai_fill_attributes(draft_id: int) -> dict:
    """AI 按草稿当前类目填属性(比 auto_map 按名硬对强，适合 1688 中文参数)。"""
    try:
        return APP.ai_fill_attributes(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
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


@app.post("/api/drafts/{draft_id}/ai-copy")
def ai_copy(draft_id: int) -> dict:
    """只生成文案(标题/简介/标签)，1 次 LLM 调用，快。结果进 ai_proposal 预览。"""
    try:
        return APP.ai_copy(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/make-infographic")
def make_infographic(draft_id: int, body: dict) -> dict:
    """把草稿某张图做成俄语信息图(+可选店铺水印)，挂回 draft.images。"""
    try:
        return APP.make_infographic(
            draft_id,
            source_index=int(body.get("source_index") or 0),
            heading=str(body.get("heading") or ""),
            bullets=body.get("bullets") or [],
            watermark=str(body.get("watermark") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/try-copy")
def try_copy(draft_id: int) -> dict:
    """Ozon 来源草稿试官方复制(import-by-sku)；可复制会在目标店建复制卡。"""
    try:
        return APP.try_copy(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/make-rich-content")
def make_rich_content(draft_id: int, body: dict | None = None) -> dict:
    """把草稿图拼成 Ozon 富文本(billboard 大图序列)，存草稿（发布时随属性 11254 上架）。"""
    try:
        return APP.make_rich_content(draft_id, image_indexes=(body or {}).get("image_indexes"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/understand")
def understand_draft(draft_id: int, body: dict | None = None) -> dict:
    """理解层:多模态看图理解 → 结构化 understanding,缓存进草稿(供文案/图片复用)。"""
    try:
        return APP.understand_draft(draft_id, force=bool((body or {}).get("force")))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/drafts/{draft_id}/recommend")
def recommend(draft_id: int) -> dict:
    """智能推荐:据来源 + understanding → 推荐路径(复制/俄化/重做)+ 逐图默认处理。"""
    try:
        return APP.recommend(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/localize-image")
def localize_image(draft_id: int, body: dict | None = None) -> dict:
    """单张俄化:图上中文→俄语(保图不变),结果进候选区。"""
    try:
        return APP.localize_image(draft_id, int((body or {}).get("source_index") or 0))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/regen-image")
def regen_image(draft_id: int, body: dict) -> dict:
    """单张重做:按角色 + 俄语文字 重新生成,结果进候选区。"""
    try:
        b = body or {}
        return APP.regen_image(draft_id, int(b.get("source_index") or 0),
                               role=str(b.get("role") or ""), heading=str(b.get("heading") or ""),
                               bullets=b.get("bullets") or [])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/whiten-main")
def whiten_main(draft_id: int, body: dict | None = None) -> dict:
    """选一张图做白底电商主图，结果进候选区。"""
    try:
        return APP.whiten_main(draft_id, int((body or {}).get("source_index") or 0))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/scene-image")
def scene_image(draft_id: int, body: dict | None = None) -> dict:
    """选一张图做场景/氛围图(保产品一致)，结果进候选区。"""
    try:
        b = body or {}
        return APP.scene_image(draft_id, int(b.get("source_index") or 0), hint=str(b.get("hint") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/drafts/{draft_id}/image-plan")
def image_plan(draft_id: int, force: bool = False) -> dict:
    """图集计划 + 每槽状态(待做/候选中/已应用)。force=true 据当前理解/图重建。"""
    try:
        return APP.image_plan(draft_id, force=bool(force))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/design-image-plan")
def design_image_plan(draft_id: int, body: dict | None = None) -> dict:
    """AI 设计图集：据看图理解+源图设计 ~target 张 Ozon 商品图方案，写入 image_plan。"""
    try:
        target = int((body or {}).get("target") or 10)
        return APP.design_image_plan(draft_id, target=target)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/generate-plan-slot")
def generate_plan_slot(draft_id: int, body: dict) -> dict:
    """生成图集计划某槽位的图，结果进候选区。"""
    try:
        return APP.generate_plan_slot(draft_id, str((body or {}).get("slot_id") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/apply-candidates")
def apply_candidates(draft_id: int, body: dict | None = None) -> dict:
    """把候选区的图加入正式图集 draft.images。不传 indices = 应用全部。"""
    try:
        return APP.apply_image_candidates(draft_id, (body or {}).get("indices") or None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/discard-candidates")
def discard_candidates(draft_id: int) -> dict:
    """清空候选区(全部丢弃)。"""
    try:
        return APP.discard_image_candidates(draft_id)
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
    from webui.media import save_upload  # noqa: PLC0415
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


@app.post("/api/ext/update-draft-media")
def ext_update_draft_media(body: dict) -> dict:
    try:
        return APP.update_draft_media(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/ext/pending-media-drafts")
def ext_pending_media_drafts() -> dict:
    return APP.pending_media_drafts()


# ---------- 出图任务 ----------
@app.post("/api/drafts/{draft_id}/gen-images-batch")
def submit_gen_images_batch(draft_id: int, body: dict) -> dict:
    try:
        return APP.submit_batch_gen_job(
            draft_id, (body or {}).get("source_indices") or [],
            str((body or {}).get("action") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/drafts/{draft_id}/copy-images-to")
def copy_images_to_target(draft_id: int, body: dict) -> dict:
    b = body or {}
    targets = b.get("target_draft_ids")
    if not targets and b.get("target_draft_id"):
        targets = [b["target_draft_id"]]
    try:
        return APP.copy_images_to_draft(draft_id, b.get("image_urls") or [], targets or [])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/drafts/{draft_id}/gallery/add")
def gallery_add(draft_id: int, body: dict) -> dict:
    return APP.gallery_add(draft_id, (body or {}).get("image_ids") or [])


@app.post("/api/drafts/{draft_id}/gallery/remove")
def gallery_remove(draft_id: int, body: dict) -> dict:
    return APP.gallery_remove(draft_id, (body or {}).get("image_ids") or [])


@app.post("/api/drafts/{draft_id}/gallery/reorder")
def gallery_reorder(draft_id: int, body: dict) -> dict:
    return APP.gallery_reorder(draft_id, (body or {}).get("image_ids") or [])


@app.delete("/api/drafts/{draft_id}/images/{image_id}")
def delete_draft_image(draft_id: int, image_id: int) -> dict:
    return APP.gallery_delete(draft_id, image_id)


@app.post("/api/gen-jobs/batch-latest")
def batch_latest_gen_jobs(body: dict) -> dict:
    return APP.batch_latest_gen_jobs((body or {}).get("draft_ids") or [])


@app.post("/api/drafts/{draft_id}/gen-images-custom")
def submit_gen_images_custom(draft_id: int, body: dict) -> dict:
    try:
        return APP.submit_gen_images_custom(draft_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/drafts/{draft_id}/gen-images")
def submit_gen_images(draft_id: int, body: dict) -> dict:
    try:
        return APP.submit_gen_job(draft_id, int((body or {}).get("target") or 10))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/gen-jobs/{job_id}")
def gen_job_status(job_id: int) -> dict:
    try:
        return APP.get_gen_job_status(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/drafts/{draft_id}/gen-job/latest")
def latest_gen_job(draft_id: int) -> dict:
    try:
        return APP.get_latest_gen_job(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# catch-all 静态挂载：托管 Vue 构建产物 frontend/dist。
# 必须放在所有 /api/* 与 /media/* 路由之后（优先级最低）。
# check_dir=False：dist 未构建时不在导入期报错，访问时由 index() 给出 503 提示。
app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True, check_dir=False), name="frontend")
