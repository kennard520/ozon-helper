"""AuthMixin —— 鉴权 / 用户管理 / 钱包 / 媒体预签名 / 发布计费。"""
from __future__ import annotations

import webui.media as _media
from ozon_common.oss import OssClient
from webui.services._helpers import _money_to_float

# 钱包出口处 Decimal→float 的字段（DAL 内部保持 Decimal 精确，仅 API 边界转 number）
_ACCOUNT_MONEY_KEYS = ("balance", "total_recharge", "total_consume")
_TXN_MONEY_KEYS = ("amount", "balance_after")


class AuthMixin:
    def auth_secret(self) -> str:
        return str(self.store.get_settings().get("jwt_secret") or "")

    def login(self, username: str, password: str) -> dict:
        from webui.auth import make_token, verify_password  # noqa: PLC0415
        user = self.store.get_user_by_username((username or "").strip())
        if not user or not verify_password(password or "", user["password_hash"]):
            raise ValueError("用户名或密码错误")
        if user.get("status") and user["status"] != "active":
            raise ValueError("账号已停用")
        token = make_token(user["id"], self.auth_secret())
        return {"token": token, "user": self._public_user(user)}

    def user_from_token(self, token: str) -> dict | None:
        from webui.auth import decode_token  # noqa: PLC0415
        payload = decode_token(token or "", self.auth_secret())
        if not payload:
            return None
        user = self.store.get_user_by_id(int(payload.get("sub", 0)))
        return self._public_user(user) if user else None

    @staticmethod
    def _public_user(user: dict) -> dict:
        return {"id": user["id"], "username": user["username"], "role": user.get("role", "user")}

    # ---------- 用户管理（仅 admin）----------
    def admin_list_users(self) -> dict:
        out = []
        for u in self.store.list_users():
            cnt = len(self.store.get_settings(u["id"]).get("ozon_stores") or [])
            out.append({**u, "store_count": cnt})
        return {"users": out}

    def admin_create_user(self, username: str, password: str, max_stores: int = 1) -> dict:
        username = (username or "").strip()
        if len(username) < 3:
            raise ValueError("用户名至少 3 个字符")
        if len(password or "") < 6:
            raise ValueError("密码至少 6 位")
        if self.store.get_user_by_username(username):
            raise ValueError("用户名已存在")
        from webui.auth import hash_password  # noqa: PLC0415
        u = self.store.create_user(username, hash_password(password),
                                   role="user", max_stores=max(1, int(max_stores)))
        return {**self._public_user(u), "max_stores": u["max_stores"], "store_count": 0}

    def admin_update_user(self, actor: dict, user_id: int,
                          max_stores: int | None = None,
                          status: str | None = None,
                          password: str | None = None) -> dict:
        target = self.store.get_user_by_id(int(user_id))
        if not target:
            raise ValueError("用户不存在")
        if status is not None:
            status = str(status).strip()
            if status not in ("active", "disabled"):
                raise ValueError("status 只能是 active/disabled")
            if status == "disabled":
                if int(actor["id"]) == int(user_id):
                    raise ValueError("不能禁用自己")
                if target.get("role") == "admin":
                    active_admins = [u for u in self.store.list_users()
                                     if u.get("role") == "admin" and (u.get("status") or "active") == "active"]
                    if len(active_admins) <= 1:
                        raise ValueError("不能禁用最后一个管理员")
            self.store.set_status(user_id, status)
        if max_stores is not None:
            self.store.set_max_stores(user_id, max(1, int(max_stores)))
        if password is not None:
            if len(password) < 6:
                raise ValueError("密码至少 6 位")
            from webui.auth import hash_password  # noqa: PLC0415
            self.store.set_password_hash(user_id, hash_password(password))
        u = self.store.get_user_by_id(int(user_id))
        cnt = len(self.store.get_settings(u["id"]).get("ozon_stores") or [])
        return {**self._public_user(u), "max_stores": u["max_stores"],
                "status": u["status"], "store_count": cnt}

    def admin_delete_user(self, actor: dict, user_id: int) -> dict:
        target = self.store.get_user_by_id(int(user_id))
        if not target:
            raise ValueError("用户不存在")
        if int(actor["id"]) == int(user_id):
            raise ValueError("不能删除自己")
        if target.get("role") == "admin":
            raise ValueError("不能删除管理员账号")
        self.store.delete_user(int(user_id))
        return {"deleted": True, "id": int(user_id)}

    # ---------- 钱包 ----------
    def wallet_state(self) -> dict:
        """当前用户钱包：账户 + 最近流水。

        钱列在 DAL 是 Decimal（精确算术），但 FastAPI JSON 编码会把 Decimal 渲染成字符串，
        前端期望 number → 出口处把钱字段 float() 化，保证 /api/wallet 返回 JSON number。
        """
        return {
            "account": _money_to_float(self.store.get_account(), _ACCOUNT_MONEY_KEYS),
            "txns": [_money_to_float(t, _TXN_MONEY_KEYS) for t in self.store.list_txns()],
        }

    def wallet_recharge(self, amount: float, remark: str = "") -> dict:
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise ValueError("金额必须是数字")
        if amount <= 0:
            raise ValueError("金额必须大于 0")
        account = self.store.recharge(amount, remark=remark or "充值")
        return {"account": _money_to_float(account, _ACCOUNT_MONEY_KEYS)}

    def presign_media(self, items: list) -> dict:
        """给插件签一批媒体的预签名 OSS 上传地址（服务级共享桶，内容哈希去重）。"""
        oss = OssClient(self.store.get_settings(), local_reader=_media.read_media_bytes)
        if not oss.configured():
            raise ValueError("未配置 OSS（服务级），无法签发上传地址")
        return {"results": oss.presign_items(items or [])}

    def publish_fee(self) -> float:
        """单次发布扣费，读全局设置 publish_fee，默认 0（不收费，旧行为不变）。"""
        try:
            return float(self.store.get_settings().get("publish_fee") or 0)
        except (TypeError, ValueError):
            return 0.0
