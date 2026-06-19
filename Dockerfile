# Ozon 上品助手后端镜像。构建上下文 = 仓库根（含 ozon-listing-webui/ 与 ozon_api/）。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/ozon-listing-webui:/app \
    WEBUI_HOST=0.0.0.0 \
    WEBUI_PORT=8585

WORKDIR /app/ozon-listing-webui

# 先装依赖（利用层缓存）。用阿里云 PyPI 镜像加速（服务器在国内）。
COPY ozon-listing-webui/requirements.txt ./requirements.txt
RUN pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 再拷代码（前端 dist 已在本地构建好，随 ozon-listing-webui 一起进来）
COPY ozon-listing-webui /app/ozon-listing-webui
COPY ozon_api /app/ozon_api

EXPOSE 8585
CMD ["python", "run_api.py"]
