"""全局 App 单例持有者（供 routers 引用，避免 routers ↔ main 循环 import）。

main.py 在构造自己的 APP = App() 后会把它写入本模块。
⚠️ routers 必须 `from webui import app_instance` 然后在 handler 里用 `app_instance.APP.xxx()`
（活模块属性，调用时查），**不要** `from webui.app_instance import APP`——那会在 import 时
把名字绑死成当时的值（None 或旧实例），测试 reload(main) 换了新 APP 后路由仍指旧实例。
"""
from __future__ import annotations

# 占位 None；main.py 导入并创建 APP 后会覆盖此处。
# 使用 Any 类型是因为此阶段尚无循环 import 风险的方式直接标注 App 类型。
APP: "App | None" = None  # type: ignore[assignment]

try:
    from webui.app_service import App  # noqa: F401 — 仅供类型注解使用
except Exception:
    App = None  # type: ignore[assignment,misc]
