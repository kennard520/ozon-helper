"""Agnes AI (Sapiens AI) 客户端：聊天(含图片理解) / 文生图·图生图 / 视频生成异步任务。

接口规格归档 specs/agnes-api/README.md（2026-06-11）。三个模型共用一个 Bearer Key：
- agnes-2.0-flash        POST {base}/v1/chat/completions   （OpenAI 兼容，content 数组带 image_url）
- agnes-image-2.1-flash  POST {base}/v1/images/generations （response_format 必须放 extra_body，顶层会 400）
- agnes-video-v2.0       POST {base}/v1/videos 创建 + GET {base}/agnesapi?video_id= 轮询
                         （查询端点不带 /v1 前缀；完成后视频 URL 在 remixed_from_video_id 字段——官方文档如此）

所有 HTTP 走模块级 _http_json（stdlib urllib），单测直接替换该属性即可离线跑。
"""
from __future__ import annotations

import base64
import json
import mimetypes
import urllib.parse

DEFAULT_BASE = "https://apihub.agnes-ai.com"
DEFAULT_CHAT_MODEL = "agnes-2.0-flash"
DEFAULT_IMAGE_MODEL = "agnes-image-2.1-flash"
DEFAULT_VIDEO_MODEL = "agnes-video-v2.0"

# 视频帧数约束：≤441 且必须满足 8n+1（81≈3s 121≈5s 241≈10s @24fps）
VIDEO_MAX_FRAMES = 441


def _conf(settings: dict, kind: str = "image") -> tuple[str, str]:
    """返回 (base, key)。base 容忍用户粘贴带 /v1 或尾斜杠的写法，统一去掉。
    kind="text" 时新 ai_text 块优先；回退到 translate_api_key；再回退到 agnes_api_key（历史兼容）。"""
    from backend.settings_migrate import ai_config  # noqa: PLC0415
    s = settings or {}
    cfg = ai_config(s, kind)
    base = (cfg["base"] or DEFAULT_BASE).strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    key = cfg["key"].strip()
    # 历史兼容：text 块回退时读 translate_api_key；但老 Agnes 配置只有 agnes_api_key
    if not key and kind == "text":
        key = str(s.get("agnes_api_key") or "").strip()
        if key:
            # base 也跟着用 agnes_api_base 兜底
            legacy_base = str(s.get("agnes_api_base") or "").strip().rstrip("/")
            if legacy_base:
                base = legacy_base
                if base.endswith("/v1"):
                    base = base[:-3].rstrip("/")
            else:
                base = DEFAULT_BASE
    if not key:
        raise RuntimeError("未配置 Agnes AI（设置页填 Agnes API Key）")
    return base, key


def _http_json(url: str, *, key: str, payload: dict | None = None, timeout: int = 60) -> dict:
    """POST(payload!=None)/GET 一个 JSON 接口。单测注入点。
    网络层错误统一包成中文 RuntimeError（路由转 400）：URLError/TimeoutError 都是
    OSError 子类，一把接住——视频冒烟实测出现过 SSL 瞬断和 60s 读超时，留原样会变成难看的 500。"""
    from urllib.error import HTTPError  # noqa: PLC0415
    from urllib.request import Request, urlopen  # noqa: PLC0415
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, method="POST" if data is not None else "GET",
                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as res:  # noqa: S310
            return json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"Agnes 接口报错 HTTP {exc.code}: {body}")
    except OSError as exc:
        raise RuntimeError(f"Agnes 网络错误（可重试）: {getattr(exc, 'reason', exc)}")


def agnes_chat(settings: dict, system: str, user: str, images: list[str] | None = None) -> str:
    """聊天补全（OpenAI 兼容）。images 给公网图片 URL 或 data URI（图片理解）。
    与 deepseek_chat 同错误契约：未配置/HTTP 错都抛 RuntimeError（路由转 400）。"""
    from backend.settings_migrate import ai_config  # noqa: PLC0415
    base, key = _conf(settings, "text")
    _s = settings or {}
    model = (ai_config(_s, "text")["model"]
             or str(_s.get("agnes_chat_model") or "").strip()
             or DEFAULT_CHAT_MODEL)
    content: object = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": u}} for u in images[:4]
        ]
    body = {
        "model": model, "temperature": 0.3, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": content}],
        # 文档建议编码/推理任务开启 thinking（OpenAI 兼容写法）
        "chat_template_kwargs": {"enable_thinking": True},
    }
    data = _http_json(f"{base}/v1/chat/completions", key=key, payload=body, timeout=180)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        # 别让裸 KeyError 逃出去——路由会把 KeyError 映成 404（语义错）
        raise RuntimeError(f"Agnes 返回格式异常: {json.dumps(data, ensure_ascii=False)[:200]}")
    return str(content or "").strip()


def generate_image(settings: dict, prompt: str, *, size: str = "1024x768",
                   source_images: list[str] | None = None) -> str:
    """文生图/图生图，返回生成图的公网 URL。
    坑（官方文档）：response_format 必须在 extra_body 里；图生图输入图也放 extra_body.image。"""
    from backend.settings_migrate import ai_config  # noqa: PLC0415
    base, key = _conf(settings, "image")
    model = (ai_config(settings, "image")["model"] or DEFAULT_IMAGE_MODEL)
    p = str(prompt or "").strip()
    if not p:
        raise ValueError("生图提示词不能为空")
    extra: dict = {"response_format": "url"}
    if source_images:
        extra["image"] = list(source_images)
    body = {"model": model, "prompt": p, "size": str(size or "1024x768"), "extra_body": extra}
    data = _http_json(f"{base}/v1/images/generations", key=key, payload=body, timeout=300)
    items = data.get("data") or []
    url = str((items[0] or {}).get("url") or "") if items else ""
    if not url:
        raise RuntimeError(f"Agnes 生图未返回图片 URL: {json.dumps(data, ensure_ascii=False)[:200]}")
    return url


def snap_num_frames(n: object) -> int:
    """把帧数收敛到合法值：≤441 且满足 8n+1。"""
    try:
        v = int(n)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        v = 121
    v = max(9, min(VIDEO_MAX_FRAMES, v))
    if v % 8 != 1:
        v = (v // 8) * 8 + 1
    return v


def create_video_task(settings: dict, prompt: str, *, image: str | list[str] | None = None,
                      num_frames: int = 121, frame_rate: int = 24,
                      width: int = 1152, height: int = 768) -> dict:
    """创建视频生成任务，返回 {video_id, task_id, status}。image 给 URL 即图生视频。"""
    from backend.settings_migrate import ai_config  # noqa: PLC0415
    base, key = _conf(settings, "video")
    model = (ai_config(settings, "video")["model"] or DEFAULT_VIDEO_MODEL)
    p = str(prompt or "").strip()
    if not p:
        raise ValueError("视频提示词不能为空")
    body: dict = {"model": model, "prompt": p, "width": int(width), "height": int(height),
                  "num_frames": snap_num_frames(num_frames),
                  "frame_rate": max(1, min(60, int(frame_rate)))}
    if image:
        body["image"] = image
    # 实测 /v1/videos 创建响应可能很慢（60s 内读超时过），给足 180s
    data = _http_json(f"{base}/v1/videos", key=key, payload=body, timeout=180)
    vid = str(data.get("video_id") or "").strip()
    tid = str(data.get("task_id") or data.get("id") or "").strip()
    if not vid and not tid:
        raise RuntimeError(f"Agnes 视频任务创建未返回 ID: {json.dumps(data, ensure_ascii=False)[:200]}")
    return {"video_id": vid or tid, "task_id": tid, "status": str(data.get("status") or "queued")}


def query_video(settings: dict, video_id: str) -> dict:
    """查询视频任务，返回 {status, progress, url, error}。
    完成后 URL 在 remixed_from_video_id（官方字段名如此），防御性兼容 video_url/url。"""
    from backend.settings_migrate import ai_config  # noqa: PLC0415
    base, key = _conf(settings, "video")
    model = (ai_config(settings, "video")["model"] or DEFAULT_VIDEO_MODEL)
    q = urllib.parse.urlencode({"video_id": video_id, "model_name": model})
    data = _http_json(f"{base}/agnesapi?{q}", key=key, timeout=60)
    url = ""
    for k in ("remixed_from_video_id", "video_url", "url"):
        v = str(data.get(k) or "")
        if v.startswith("http"):
            url = v
            break
    err = data.get("error")
    return {"status": str(data.get("status") or ""),
            "progress": int(data.get("progress") or 0),
            "url": url,
            "error": "" if err in (None, "") else str(err)}


def to_data_uri(data: bytes, filename: str = "") -> str:
    """本地图片字节 → data URI（图生图接受 Data URI Base64，公网拿不到本地 /media/ 时用）。"""
    mime = mimetypes.guess_type(filename or "")[0] or "image/png"
    if not mime.startswith("image/"):
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def pick_public_images(images: list | None, detail_images: list | None = None, cap: int = 3) -> list[str]:
    """从草稿图集挑公网可达的 http(s) URL 给视觉理解用（本地 /media/ 外网不可达，跳过）。
    主图集优先、详情图补足，去重，最多 cap 张。"""
    out: list[str] = []
    seen: set[str] = set()
    for u in list(images or []) + list(detail_images or []):
        s = str(u or "").strip()
        if s.startswith("http") and s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= cap:
            break
    return out
