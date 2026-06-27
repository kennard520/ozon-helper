"""全局 App 单例持有者（供 routers 引用，避免 routers ↔ main 循环 import）。

main.py 在构造自己的 APP = App() 后会把它写入本模块，
routers 通过 `from webui.app_instance import APP` 拿到的是 main 的那个实例。
"""
from __future__ import annotations

# 占位 None；main.py 导入并创建 APP 后会覆盖此处。
# 使用 Any 类型是因为此阶段尚无循环 import 风险的方式直接标注 App 类型。
APP: "App | None" = None  # type: ignore[assignment]

try:
    from webui.app_service import App  # noqa: F401 — 仅供类型注解使用
except Exception:
    App = None  # type: ignore[assignment,misc]
