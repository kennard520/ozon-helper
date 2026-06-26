"""阿里云 OSS 对象存储：upload_bytes（内容 MD5 幂等上传），供 worker 传生成图。独立模块。"""

from __future__ import annotations

import hashlib
import os


def _clean(v: object) -> str:
    s = str(v or "").strip()
    # 去掉 JSON 双引号包裹（DB 值可能是 "oss-cn-beijing.aliyuncs.com"）
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    return s


class OssClient:
    def __init__(self, *, endpoint: str = "", bucket_name: str = "",
                 access_key_id: str = "", access_key_secret: str = "",
                 public_base: str = ""):
        self.endpoint = (_clean(endpoint) or _clean(os.environ.get("OSS_ENDPOINT"))).replace("https://", "").replace("http://", "").rstrip("/")
        self.bucket_name = _clean(bucket_name) or _clean(os.environ.get("OSS_BUCKET"))
        self.ak = _clean(access_key_id) or _clean(os.environ.get("OSS_ACCESS_KEY_ID"))
        self.sk = _clean(access_key_secret) or _clean(os.environ.get("OSS_ACCESS_KEY_SECRET"))
        self.public_base = (_clean(public_base) or _clean(os.environ.get("OSS_PUBLIC_BASE"))).rstrip("/")

    def configured(self) -> bool:
        return all([self.endpoint, self.bucket_name, self.ak, self.sk])

    def _bucket_obj(self):
        import oss2
        auth = oss2.Auth(self.ak, self.sk)
        return oss2.Bucket(auth, f"https://{self.endpoint}", self.bucket_name)

    def _default_domain(self) -> str:
        return f"https://{self.bucket_name}.{self.endpoint}"

    def _public_url(self, key: str) -> str:
        base = self.public_base or self._default_domain()
        return f"{base}/{key}"

    def upload_bytes(self, data: bytes, ext: str) -> str:
        key = f"ozon-media/{hashlib.md5(data).hexdigest()}.{(ext or 'bin').lstrip('.')}"
        b = self._bucket_obj()
        if not b.object_exists(key):
            b.put_object(key, data)
        return self._public_url(key)
