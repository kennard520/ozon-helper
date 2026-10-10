"""启动后端（console_script: ozon-webui → server:main）。
- 开发(本机)：python -m uv run --package ozon-webui ozon-webui [port]；不带参数从候选端口自动挑（Windows 保留端口多）。
- 服务器部署：设环境变量 WEBUI_HOST=0.0.0.0 WEBUI_PORT=8585，则按固定 host/port 监听
  （给 Caddy/Nginx 反代用），不再自动选端口。"""
from __future__ import annotations

import logging
import os
import socket
import sys
from pathlib import Path

# 在 uvicorn 接管之前先配好应用日志（uvicorn 不改我们的 logger）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ozon] %(levelname)s %(message)s",
    stream=sys.stderr,
    force=True,
)

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402
from ozon_common.runtime import is_local_lite  # noqa: E402

CANDIDATE_PORTS = [8585, 8787, 5050, 7373, 6464, 9911, 8123, 5151, 19283, 28282]


def _can_bind(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick_port(argv: list[str]) -> int | None:
    if len(argv) > 1:
        try:
            return int(argv[1])
        except ValueError:
            return None
    for p in CANDIDATE_PORTS:
        if _can_bind(p):
            return p
    return None


def main() -> int:
    # 服务器部署：WEBUI_HOST 一旦设置（如 0.0.0.0）就按固定 host/port 监听，不自动选端口
    host_env = None if is_local_lite() else os.environ.get("WEBUI_HOST")
    log = logging.getLogger("ozon")
    if host_env:
        port = int(os.environ.get("WEBUI_PORT") or 8585)
        log.info(f"部署模式: 监听 {host_env}:{port}")
        uvicorn.run("webui.main:app", host=host_env, port=port, reload=False)
        return 0
    # 本机开发：自动挑端口，绑 127.0.0.1，插件自动发现
    port = pick_port(sys.argv)
    if port is None:
        log.error("所有候选端口都无法绑定")
        return 1
    log.info(f"开发模式: 端口={port}")
    if is_local_lite():
        import threading
        import time
        import urllib.request
        import webbrowser

        def open_when_ready():
            url = f"http://127.0.0.1:{port}"
            for _ in range(60):
                try:
                    with urllib.request.urlopen(url + "/api/ext/ping", timeout=1):
                        webbrowser.open(url)
                    return
                except OSError:
                    time.sleep(1)
            log.error("本地服务未就绪，请查看启动日志")

        threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run("webui.main:app", host="127.0.0.1", port=port, reload=False)
    return 0
    uvicorn.run("webui.main:app", host="127.0.0.1", port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
