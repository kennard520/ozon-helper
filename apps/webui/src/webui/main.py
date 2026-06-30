from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from webui.app_service import FRONTEND_DIST, App
from webui.media import media_file
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
from webui.routers import (  # noqa: E402
    ai_image as ai_image_router,
    ai_text as ai_text_router,
    ai_video as ai_video_router,
    analytics as analytics_router,
    auth as auth_router,
    category as category_router,
    drafts as drafts_router,
    ext as ext_router,
    gallery as gallery_router,
    pricing as pricing_router,
    publish as publish_router,
    settings as settings_router,
    warehouse as warehouse_router,
)
app.include_router(auth_router.router)
app.include_router(settings_router.router)
app.include_router(category_router.router)
app.include_router(drafts_router.router)
app.include_router(publish_router.router)
app.include_router(ai_text_router.router)
app.include_router(ai_image_router.router)
app.include_router(ai_video_router.router)
app.include_router(gallery_router.router)
app.include_router(ext_router.router)
app.include_router(pricing_router.router)
app.include_router(warehouse_router.router)
app.include_router(analytics_router.router)


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

# catch-all 静态挂载：托管 Vue 构建产物 frontend/dist。
# 必须放在所有 /api/* 与 /media/* 路由之后（优先级最低）。
# check_dir=False：dist 未构建时不在导入期报错，访问时由 index() 给出 503 提示。
app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True, check_dir=False), name="frontend")
