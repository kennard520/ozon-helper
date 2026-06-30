"""JSON / 时间小工具(跨 webui 与 worker 共用)。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def loads_json(text: object, default=None):
    if not text:
        return default
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(str(text))
    except (TypeError, ValueError):
        return default
