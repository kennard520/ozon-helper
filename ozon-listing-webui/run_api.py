"""启动后端。
- 开发(本机)：python run_api.py [port]；不带参数从候选端口自动挑（Windows 保留端口多）。
- 服务器部署：设环境变量 WEBUI_HOST=0.0.0.0 WEBUI_PORT=8585，则按固定 host/port 监听
  （给 Caddy/Nginx 反代用），不再自动选端口。"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

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
    host_env = os.environ.get("WEBUI_HOST")
    if host_env:
        port = int(os.environ.get("WEBUI_PORT") or 8585)
        print(f">>> 后端固定监听 {host_env}:{port}（部署模式，反代到这里）")
        uvicorn.run("backend.main:app", host=host_env, port=port, reload=False)
        return 0
    # 本机开发：自动挑端口，绑 127.0.0.1，插件自动发现
    port = pick_port(sys.argv)
    if port is None:
        print("\n!!! 所有候选端口都无法绑定（WinError 10013 等）。")
        print("!!! 多半是防火墙/杀毒拦了 python 联网，请在防火墙里放行 python 后重试。\n")
        return 1
    print("\n" + "=" * 52)
    print(f">>>  Ozon 助手后端端口 = {port}")
    print(">>>  插件会自动找到它，无需手动改端口。")
    print("=" * 52 + "\n")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
