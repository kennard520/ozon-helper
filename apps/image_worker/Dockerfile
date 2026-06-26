# 构建上下文 = 仓库根(需带上 packages/ozon_common)
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ozon_common/pyproject.toml packages/ozon_common/
COPY apps/image_worker/pyproject.toml apps/image_worker/
RUN uv sync --package ozon-image-worker --no-dev --frozen --no-install-project
COPY packages/ozon_common packages/ozon_common
COPY apps/image_worker apps/image_worker
RUN uv sync --package ozon-image-worker --no-dev --frozen
CMD ["uv", "run", "--package", "ozon-image-worker", "ozon-worker"]
