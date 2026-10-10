# Ozon 上品助手 webui 镜像。构建上下文 = 仓库根。
# 前端需在本机先 build：cd apps/webui/frontend && npm run build
# 然后用 scripts/build_and_deploy.sh 打包（包含 dist/），或手动将 dist 加入 tarball。
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 \
    UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    WEBUI_HOST=0.0.0.0 \
    WEBUI_PORT=8585
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ozon_common/pyproject.toml packages/ozon_common/
COPY packages/ozon_api/pyproject.toml packages/ozon_api/
COPY apps/webui/pyproject.toml apps/webui/
COPY apps/image_worker/pyproject.toml apps/image_worker/
COPY apps/mcp_server/pyproject.toml apps/mcp_server/
# hatchling editable build 需要能找到 src 目录，提前 COPY src（供第一次 uv sync 使用）
COPY packages/ozon_common/src packages/ozon_common/src
COPY packages/ozon_api/src packages/ozon_api/src
RUN uv sync --package ozon-webui --package ozon-image-worker --package ozon-mcp --no-dev --frozen --no-install-project
COPY packages packages
COPY alembic.ini alembic.ini
COPY migrations migrations
COPY apps/webui apps/webui
COPY apps/image_worker apps/image_worker
COPY apps/mcp_server apps/mcp_server
# 前端构建产物（本机 npm run build 后随 tarball 一起传）
COPY apps/webui/frontend/dist apps/webui/frontend/dist
RUN uv sync --package ozon-webui --package ozon-image-worker --package ozon-mcp --no-dev --frozen
EXPOSE 8585 8586
CMD ["uv", "run", "--package", "ozon-webui", "ozon-webui"]
