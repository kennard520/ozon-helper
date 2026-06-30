"""阿里云 OSS（oss2）对象存储封装：内容 MD5 当 key 幂等上传。
bucket 可注入便于单测（不依赖真实 oss2/网络）。"""
from __future__ import annotations

import hashlib
import mimetypes
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _clean(v: object) -> str:
    return str(v or "").strip()


class OssClient:
    def __init__(self, settings: dict, *, bucket=None):
        s = settings or {}
        self.endpoint = _clean(s.get("oss_endpoint")).replace("https://", "").replace("http://", "").rstrip("/")
        self.bucket_name = _clean(s.get("oss_bucket"))
        self.ak = _clean(s.get("oss_access_key_id"))
        self.sk = _clean(s.get("oss_access_key_secret"))
        self.public_base = _clean(s.get("oss_public_base")).rstrip("/")
        self._bucket = bucket

    def configured(self) -> bool:
        return all([self.endpoint, self.bucket_name, self.ak, self.sk])

    def _bucket_obj(self):
        if self._bucket is None:
            import oss2  # noqa: PLC0415
            auth = oss2.Auth(self.ak, self.sk)
            self._bucket = oss2.Bucket(auth, f"https://{self.endpoint}", self.bucket_name)
        return self._bucket

    def _default_domain(self) -> str:
        return f"https://{self.bucket_name}.{self.endpoint}"

    def _public_url(self, key: str) -> str:
        base = self.public_base or self._default_domain()
        return f"{base}/{key}"

    def _on_oss(self, url: str) -> bool:
        if not url:
            return False
        base = self.public_base or self._default_domain()
        return url.startswith(base + "/")

    def public_url(self, key: str) -> str:
        return self._public_url(key)

    # ---- 服务器侧用「内网 endpoint」取对象，给 /oss 图片代理用（免 OSS 外网出流量）----
    def _internal_endpoint(self) -> str:
        env = _clean(os.environ.get("OZON_OSS_INTERNAL_ENDPOINT"))
        if env:
            return env.replace("https://", "").replace("http://", "").rstrip("/")
        ep = self.endpoint
        # 外网 endpoint 自动推内网：oss-cn-x.aliyuncs.com -> oss-cn-x-internal.aliyuncs.com
        if ep.endswith(".aliyuncs.com") and "-internal" not in ep:
            return ep.replace(".aliyuncs.com", "-internal.aliyuncs.com")
        return ep

    def _internal_bucket(self):
        import oss2  # noqa: PLC0415
        auth = oss2.Auth(self.ak, self.sk)
        return oss2.Bucket(auth, f"https://{self._internal_endpoint()}", self.bucket_name)

    def get_object(self, key: str) -> tuple[bytes, str]:
        """走内网 endpoint 取对象（北京 ECS↔北京 OSS 内网免费）。返回 (data, content_type)。"""
        obj = self._internal_bucket().get_object(key)
        data = obj.read()
        ct = ""
        try:
            ct = obj.headers.get("Content-Type") or obj.headers.get("content-type") or ""
        except Exception:
            ct = ""
        if not ct or ct == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(key)
            ct = guessed or ct or "application/octet-stream"
        return data, ct

    def object_exists(self, key: str) -> bool:
        return bool(self._bucket_obj().object_exists(key))

    def presign_put(self, key: str, *, content_type: str | None = None, expires: int = 600) -> str:
        """生成预签名 PUT 地址，客户端(插件)凭它直传 OSS，服务器不过字节。"""
        headers = {"Content-Type": content_type} if content_type else None
        return self._bucket_obj().sign_url("PUT", key, int(expires), headers=headers, slash_safe=True)

    def presign_items(self, items: list) -> list:
        """给一批内容哈希 key 签预签名上传地址；已存在的不签(去重)。
        只允许 ozon-media/ 前缀(内容哈希命名)，防客户端越权覆盖他人对象。
        返回 [{key, url(最终公网), upload_url(预签名PUT, 已存在则 None)}]。"""
        out = []
        for it in items or []:
            key = _clean((it or {}).get("key"))
            if not key.startswith("ozon-media/"):
                continue
            ct = _clean((it or {}).get("content_type")) or None
            if self.object_exists(key):
                out.append({"key": key, "url": self._public_url(key), "upload_url": None})
            else:
                out.append({"key": key, "url": self._public_url(key),
                            "upload_url": self.presign_put(key, content_type=ct)})
        return out

    def upload_bytes(self, data: bytes, ext: str) -> str:
        key = f"ozon-media/{hashlib.md5(data).hexdigest()}.{(ext or 'bin').lstrip('.')}"
        b = self._bucket_obj()
        if not b.object_exists(key):
            b.put_object(key, data)
        return self._public_url(key)

    def upload_remote(self, url: str) -> str:
        u = _clean(url)
        if not u or self._on_oss(u):
            return u
        if u.startswith("/media/") or not u.startswith("http"):
            from backend.media import read_media_bytes  # noqa: PLC0415
            media_url = u if u.startswith("/media/") else ("/media/" + u.lstrip("/"))
            data = read_media_bytes(media_url)   # read_media_bytes 需要带 /media/ 前缀(它内部再剥)
            if data is None:
                raise RuntimeError(f"本地媒体读不到: {u}")
            ext = os.path.splitext(media_url)[1].lstrip(".") or "jpg"
            return self.upload_bytes(data, ext)
        req = Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=60) as resp:  # noqa: S310
            data = resp.read()
        ext = os.path.splitext(urlparse(u).path)[1].lstrip(".") or "jpg"
        return self.upload_bytes(data, ext)
