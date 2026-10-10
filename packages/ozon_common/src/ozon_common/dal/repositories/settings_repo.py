from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, insert, select

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import settings as T

# 与 apps/webui/src/webui/store.py::GLOBAL_SETTING_KEYS 保持同步:
# 这些 key 无论 user_id 传什么,一律写入 user_id=0(系统全局)。
GLOBAL_SETTING_KEYS: frozenset[str] = frozenset({
    "jwt_secret",
    "oss_endpoint", "oss_bucket", "oss_access_key_id", "oss_access_key_secret", "oss_public_base",
})


def _decode(v: Any) -> Any:
    """反序列化存储值,语义对齐旧 Store: loads_json(value, value)。

    旧 Store 写时对所有值 json.dumps(字符串也带引号存,如 "2" → '"2"'),
    读时一律 json.loads、失败回退原值。故这里也对全部字符串值 json.loads:
      '"2"' → "2"(字符串保形)、'0.1' → 0.1、'{...}' → dict、裸串解析失败 → 原样。
    """
    if not isinstance(v, str):
        return v
    try:
        return json.loads(v)
    except (json.JSONDecodeError, TypeError):
        return v


class SettingsRepo(BaseRepo):
    def get_settings(self, user_id: int = 1) -> dict[str, Any]:
        """读取全局(user_id=0)与指定用户设置的合并结果;用户设置覆盖全局。

        语义与 Store.get_settings 等价:
          SELECT key, value FROM settings WHERE user_id IN (0, ?) — 后写者覆盖。
        """
        out: dict[str, Any] = {}
        rows = self.s.execute(
            select(T.c.user_id, T.c.key, T.c.value).where(
                T.c.user_id.in_([0, int(user_id)])
            ).order_by(T.c.user_id)  # user_id=0 先,user_id=N 后写可覆盖
        ).all()
        for _uid, k, v in rows:
            out[k] = _decode(v)
        return out

    def save_settings(self, values: dict[str, Any], user_id: int = 1) -> dict[str, Any]:
        """写设置:全局键(GLOBAL_SETTING_KEYS)落 user_id=0,其余落 user_id。

        实现用 delete+insert 保证幂等覆盖,语义与 Store.save_settings 等价
        (Store 用 INSERT ... ON CONFLICT DO UPDATE;两者写后读结果相同)。
        注:若有事务内多次写同一 key,本实现同样正确(先删后插)。
        """
        uid = int(user_id)
        for k, v in values.items():
            target_uid = 0 if k in GLOBAL_SETTING_KEYS else uid
            # 对齐旧 Store dumps_json:所有值(含字符串)一律 json.dumps,
            # 这样字符串带引号存、读时 json.loads 能保形(如 "2" 不被当成 int 2)。
            sv = json.dumps(v, ensure_ascii=False, separators=(",", ":"), default=str)
            self.s.execute(delete(T).where(T.c.user_id == target_uid, T.c.key == k))
            self.s.execute(insert(T).values(user_id=target_uid, key=k, value=sv))
        return self.get_settings(uid)
