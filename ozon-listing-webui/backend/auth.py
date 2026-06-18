"""多用户鉴权：纯 stdlib 实现，不引 passlib/pyjwt。

- 密码：PBKDF2-HMAC-SHA256，存 `pbkdf2_sha256$iter$salt_hex$hash_hex`。
- 令牌：HS256 JWT（hmac+sha256 自签），含 sub(user_id) 与 exp。
所有函数纯函数/可单测；FastAPI 依赖在 main.py 用本模块 + APP.store 组装。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

_PBKDF2_ITERS = 200_000
_TOKEN_TTL = 7 * 24 * 3600  # 7 天


# ---------- 密码哈希 ----------
def hash_password(password: str, *, iterations: int = _PBKDF2_ITERS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = str(stored).split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ---------- JWT (HS256) ----------
def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def make_token(user_id: int, secret: str, *, ttl: int = _TOKEN_TTL, now: int | None = None) -> str:
    now = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": int(user_id), "iat": now, "exp": now + ttl}
    seg = _b64u(json.dumps(header, separators=(",", ":")).encode()) + "." + \
        _b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode("utf-8"), seg.encode("ascii"), hashlib.sha256).digest()
    return seg + "." + _b64u(sig)


def decode_token(token: str, secret: str, *, now: int | None = None) -> dict | None:
    """校验签名+过期，返回 payload；任何不合法返回 None。"""
    try:
        seg_h, seg_p, seg_s = str(token).split(".")
    except (ValueError, AttributeError):
        return None
    signing_input = (seg_h + "." + seg_p).encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        given = _b64u_decode(seg_s)
    except Exception:  # noqa: BLE001
        return None
    if not hmac.compare_digest(expected, given):
        return None
    try:
        payload = json.loads(_b64u_decode(seg_p))
    except Exception:  # noqa: BLE001
        return None
    now = int(now if now is not None else time.time())
    if int(payload.get("exp", 0)) < now:
        return None
    return payload
