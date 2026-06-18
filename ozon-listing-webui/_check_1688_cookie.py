# -*- coding: utf-8 -*-
"""查 .auth/1688_profile 到底有没有 1688 登录态。
登录标志 cookie：unb(登录用户数字 id) / lid(登录名) / _nk_ / cookie2 / _l_g_ / sgcookie。
有 unb 基本就是已登录。"""
import sys
sys.path.insert(0, 'tools/ozon-scraper')
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from cloakbrowser import launch_persistent_context

PROF = Path('.auth/1688_profile')
print("profile 存在:", PROF.exists(), "| 路径:", PROF.resolve())

ctx = launch_persistent_context(str(PROF), headless=True, locale="zh-CN", timezone="Asia/Shanghai")
try:
    cookies = ctx.cookies()
finally:
    ctx.close()

rel = [c for c in cookies if any(d in (c.get("domain") or "")
       for d in ("1688.com", "taobao.com", "alibaba.com", "alicdn", "tmall"))]
print("相关域 cookie 总数:", len(rel))

login_markers = ("unb", "lid", "_nk_", "cookie2", "_l_g_", "sgcookie", "havana_lgc2_77")
found = {}
for c in rel:
    n = c.get("name", "")
    if n in login_markers:
        v = c.get("value", "")
        found[n] = (v[:18] + "…") if len(v) > 18 else v
print("登录标志 cookie:", found if found else "【无 —— 未登录】")
print("\n判定:", "已登录 ✓" if ("unb" in found or "lid" in found or "_nk_" in found) else "未登录 ✗（detail 页靠匿名放行才采到数据）")
