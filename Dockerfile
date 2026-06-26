# Ozon 上品助手 webui 镜像。构建上下文 = 仓库根。
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
RUN uv sync --package ozon-webui --no-dev --frozen --no-install-project
COPY packages packages
COPY apps/webui apps/webui
RUN uv sync --package ozon-webui --no-dev --frozen
EXPOSE 8585
CMD ["uv", "run", "--package", "ozon-webui", "ozon-webui"]
