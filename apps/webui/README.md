# Ozon 上品助手 WebUI

本地运行的 Ozon 一键上品 MVP。

第一版支持：

- 粘贴 1688 商品链接，一行一个。
- 生成本地 Ozon 商品草稿。
- 在 WebUI 中补齐标题、描述、类目、价格、库存、图片、属性。
- 保存 Ozon `Client-Id` / `Api-Key` 到本地 SQLite。
- 发布草稿到 Ozon Seller API `POST /v3/product/import`。

## 架构（P0b 起）

- **后端 FastAPI**：`backend/`（`main.py` 路由 / `app_service.py` App / `models.py`）+ 顶层领域模块（`store.py` / `drafts.py` / `collector*.py` / `ozon_client_adapter.py` / `media.py` / `catalog.py`）。
- **前端 Vue3 + Vite + Element Plus**：`frontend/`，构建到 `frontend/dist/` 由 FastAPI 托管。
- 旧原生 JS 前端（`static/`）与旧入口（`server.py`）已于 P0b 下线。

## 运行

**首次 / 改完前端后必须先构建**（`frontend/dist/` 是构建产物，不入库）：

```powershell
cd tools\ozon-listing-webui\frontend
npm install        # 首次
npm run build      # 产出 frontend/dist/
```

启动后端（托管 dist）：

```powershell
$env:PYTHONPATH = "tools/ozon-listing-webui"
python tools/ozon-listing-webui/run_api.py        # 默认 8787 → http://127.0.0.1:8787
python tools/ozon-listing-webui/run_api.py 8790   # 换端口
```

前端开发热更新（dev server 代理 `/api`、`/media` 到后端 8787）：

```powershell
cd tools\ozon-listing-webui\frontend
npm run dev
```

## 本地数据

- SQLite：`tools/ozon-listing-webui/data/products.db`
- 1688 profile 预留目录：`.auth/1688_profile`

## 测试

后端：

```powershell
$env:PYTHONPATH = "tools/ozon-listing-webui"
python -m unittest discover -s tools\ozon-listing-webui\tests
python -m compileall -q tools\ozon-listing-webui\backend
```

前端：

```powershell
cd tools\ozon-listing-webui\frontend
npm run test
```

