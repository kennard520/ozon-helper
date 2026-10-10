"""官方复制（import-by-sku）流程：试复制 → 轮询 import/info → 判定是否可复制。

纯逻辑 + 可注入 client/sleep，便于单测。copyable=False 时调用方应转「原创建卡」分支。
"""
from __future__ import annotations

import time as _time
from typing import Any, Callable

# 源卡主开了「禁止复制内容」时，Ozon 在 unmatched_sku_list 或导入 errors 文案/错误码里给出的信号
_PROHIBIT_HINTS = ("copy", "копиров", "prohibit", "запрещ", "запрет")
# 复制成功（卡片已建，moderating=审核中也算建成）
_SUCCESS_STATUSES = ("imported", "moderating")
# 仍在处理，继续轮询
_PENDING_STATUSES = ("pending", "not_started", "")


def build_copy_item(
    *, sku: Any, offer_id: Any, price: Any = None, name: str = "",
    old_price: Any = None, currency_code: str = "", vat: Any = None,
) -> dict[str, Any]:
    """组装 import-by-sku 的单个 item；空的可选字段不带。sku 转 int，金额转 str。"""
    item: dict[str, Any] = {"sku": int(sku), "offer_id": str(offer_id)}
    if name:
        item["name"] = str(name)
    if price not in (None, ""):
        item["price"] = str(price)
    if old_price not in (None, ""):
        item["old_price"] = str(old_price)
    if currency_code:
        item["currency_code"] = str(currency_code)
    if vat not in (None, ""):
        item["vat"] = str(vat)
    return item


def _is_copy_prohibited(text: str) -> bool:
    t = str(text or "").lower()
    return any(h in t for h in _PROHIBIT_HINTS)


def import_verdict(sku: int, import_response: dict[str, Any]) -> dict[str, Any]:
    """解读 import-by-sku 的同步返回 → {task_id, unmatched, copyable}。
    copyable=False 表示该 sku 当场被拒（多为源卡禁止复制 / 无 task_id）。"""
    result = import_response.get("result") or {}
    unmatched = [int(x) for x in (result.get("unmatched_sku_list") or []) if str(x).strip()]
    task_id = result.get("task_id")
    copyable = bool(task_id) and int(sku) not in unmatched
    return {"task_id": task_id, "unmatched": unmatched, "copyable": copyable}


def poll_verdict(poll_info: dict[str, Any]) -> dict[str, Any]:
    """解读 import/info 的一次轮询 → {settled, status, copyable, errors}。
    status ∈ created | prohibited | failed | pending。"""
    items = (poll_info.get("result") or {}).get("items") or []
    statuses = [str(it.get("status") or "") for it in items]
    errors = [e for it in items for e in (it.get("errors") or [])]
    err_text = " ".join(
        str(e.get("message") or e.get("code") or e) if isinstance(e, dict) else str(e)
        for e in errors
    )
    if errors and _is_copy_prohibited(err_text):
        return {"settled": True, "status": "prohibited", "copyable": False, "errors": errors}
    if not statuses or any(s in _PENDING_STATUSES for s in statuses):
        return {"settled": False, "status": "pending", "copyable": True, "errors": errors}
    if all(s in _SUCCESS_STATUSES for s in statuses):
        return {"settled": True, "status": "created", "copyable": True, "errors": errors}
    return {"settled": True, "status": "failed", "copyable": False, "errors": errors}


def copy_by_sku(
    client: Any, *, sku: Any, offer_id: Any, price: Any = None, name: str = "",
    old_price: Any = None, currency_code: str = "", vat: Any = None,
    poll_times: int = 10, poll_interval: float = 2.0,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """官方复制：试 import-by-sku → 轮询 import/info。

    返回 {copyable, status, task_id, response, poll, errors}：
      - status=created   → 复制成功（已建卡 / 审核中）
      - status=pending   → 已建任务但轮询超时未确认（保留 task_id 后续再查），copyable=True
      - status=not_copyable / prohibited / failed → copyable=False，调用方转「原创建卡」分支
    client 需有 import_by_sku(items) 与 get_import_info(task_id)。sleep 可注入便于测试。
    """
    sleep = sleep or _time.sleep
    item = build_copy_item(
        sku=sku, offer_id=offer_id, price=price, name=name,
        old_price=old_price, currency_code=currency_code, vat=vat)
    response = client.import_by_sku([item])
    iv = import_verdict(int(sku), response)
    if not iv["copyable"]:
        return {"copyable": False, "status": "not_copyable", "task_id": iv["task_id"],
                "unmatched": iv["unmatched"], "response": response, "poll": {}, "errors": []}

    task_id = iv["task_id"]
    last_poll: dict[str, Any] = {}
    for _ in range(max(1, int(poll_times))):
        sleep(poll_interval)
        last_poll = client.get_import_info(int(task_id))
        pv = poll_verdict(last_poll)
        if pv["settled"]:
            return {"copyable": pv["copyable"], "status": pv["status"], "task_id": task_id,
                    "response": response, "poll": last_poll, "errors": pv["errors"]}
    return {"copyable": True, "status": "pending", "task_id": task_id,
            "response": response, "poll": last_poll or {"warning": "poll timeout"}, "errors": []}
