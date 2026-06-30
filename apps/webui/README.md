# Ozon 上品助手 WebUI

Ozon 一键上品工具(FastAPI + Vue3)。粘 1688 链接 → 生成草稿 → 工作台补齐标题/类目/属性/图片/价 → AI 文案与出图 → 发布到 Ozon Seller API。本包是 monorepo 的 `apps/webui`。

## 架构
- **后端 FastAPI**:`src/webui/`。`main.py`=装配层(建 app + 12 个 `routers/` + 中间件 + SPA 挂载);`app_service.py`=薄 facade `class App`(组合 `services/` 下 13 个领域 mixin);`app_instance.py`=APP 单例。详见 [docs/product/backend-architecture.md](../../docs/product/backend-architecture.md)。
- **数据层**:`packages/ozon_common`(SQLAlchemy Core + Repository/UoW + Alembic),本地 SQLite、服务器 MySQL(`OZON_MYSQL_*` env 自动切)。
- **前端 Vue3 + Vite + Element Plus**:`frontend/`,构建到 `frontend/dist/`(不入库)由 FastAPI 托管。设计系统见 `frontend/src/styles/tokens.css` + `frontend/src/ui/`。

## 运行(本地,仓库根目录)
> uv 不在 PATH 时用 `python -m uv`。

```bash
# 后端(默认 SQLite apps/webui/src/webui/data/products.db;自动选端口/默认 8585)
python -m uv run --package ozon-webui ozon-webui
# 或显式 uvicorn:
python -m uv run uvicorn webui.main:app --port 8585 --app-dir apps/webui/src
```

```bash
# 前端(首次/改完前端必构建——dist 是产物不入库)
cd apps/webui/frontend
npm install          # 首次
npm run build        # 产出 dist/(后端托管)
npm run dev          # 开发热更新(vite proxy /api、/media 到后端)
```

## 测试
```bash
# 后端(仓库根)
python -m uv run python -m pytest apps/webui/tests --ignore-glob='*_live.py' -q
# 全套(含 packages):
python -m uv run python -m pytest apps/webui/tests packages --ignore-glob='*_live.py' -q
# 前端
cd apps/webui/frontend && npm run test
```

## 本地数据 / 配置
- SQLite:`apps/webui/src/webui/data/products.db`(含 jwt_secret + 草稿,**敏感**)。
- Ozon 凭证:「设置→Ozon 店铺」填 Client-Id/Api-Key(多店存 `settings.ozon_stores`)。
- 部署(Docker + MySQL):见 [deploy/DEPLOY.md](deploy/DEPLOY.md)。
