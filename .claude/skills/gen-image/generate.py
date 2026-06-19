#!/usr/bin/env python3
"""
gen-image skill 抓数脚本：调用 gptplus5 网关用 gpt-image-2-2 生成图片。
纯标准库，无第三方依赖（与 ozon-stats 风格一致）。

两种模式（按有无 --image 自动选）：
  text2img:  python generate.py "一只戴帽子的柴犬"
  img2img :  python generate.py "改成纯白底电商主图" --image src.png

常用参数：
  --model   默认 gpt-image-2-2，可换 gpt-image-2 等
  --n       生成张数（默认 1）
  --size    可选，如 1024x1024 / 1024x1536 / 1536x1024
  --out     输出目录（默认 .claude/skills/gen-image/output）
  --name    文件名前缀（默认按时间戳）

结果：图片存到 --out，并把清单（含 token 用量）写到本目录 _last.json，
      stdout 打一行 OK/ERROR 状态。Windows 控制台可能把中文打乱码，
      取数请用 Read 读 _last.json，别从 stdout 解析。
"""

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

BASE_URL = os.environ.get("GPTPLUS5_BASE_URL", "https://az.gptplus5.com/v1").rstrip("/")


def _load_api_key():
    """key 优先读环境变量 GPTPLUS5_API_KEY；否则读本目录下未入库的
    _secret.json（格式 {"api_key": "sk-..."}）。绝不把密钥写进本文件——会随仓库泄露。"""
    key = os.environ.get("GPTPLUS5_API_KEY")
    if key:
        return key.strip()
    p = os.path.join(HERE, "_secret.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return (json.load(f).get("api_key") or "").strip()
        except Exception:
            pass
    return ""


API_KEY = _load_api_key()

DEFAULT_MODEL = "gpt-image-2-2"


def _auth_headers(extra=None):
    if not API_KEY:
        raise SystemExit(
            "ERROR 缺少 API key：设置环境变量 GPTPLUS5_API_KEY，或在 "
            ".claude/skills/gen-image/_secret.json 写 {\"api_key\": \"sk-...\"}"
        )
    h = {"Authorization": "Bearer " + API_KEY}
    if extra:
        h.update(extra)
    return h


def _post(url, data, headers, retries=4):
    """POST，带 429/5xx 退避重试。返回解析后的 JSON。"""
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            last = f"HTTP {e.code}: {body[:300]}"
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(6 * (attempt + 1))
                continue
            raise RuntimeError(last)
        except urllib.error.URLError as e:
            last = f"URLError: {e}"
            if attempt < retries - 1:
                time.sleep(6 * (attempt + 1))
                continue
            raise RuntimeError(last)
    raise RuntimeError(last or "未知错误")


def _multipart(fields, files):
    """构造 multipart/form-data。files: {name: filepath}。返回 (body_bytes, content_type)。"""
    boundary = "----genimage" + str(int(time.time() * 1000))
    bb = boundary.encode()
    out = b""
    for k, v in fields.items():
        out += b"--" + bb + b"\r\n"
        out += ('Content-Disposition: form-data; name="%s"\r\n\r\n' % k).encode()
        out += str(v).encode("utf-8") + b"\r\n"
    for k, path in files.items():
        fn = os.path.basename(path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            content = f.read()
        out += b"--" + bb + b"\r\n"
        out += ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (k, fn)).encode()
        out += ("Content-Type: %s\r\n\r\n" % mime).encode()
        out += content + b"\r\n"
    out += b"--" + bb + b"--\r\n"
    return out, "multipart/form-data; boundary=" + boundary


def text2img(prompt, model, n, size):
    payload = {"model": model, "prompt": prompt, "n": n}
    if size:
        payload["size"] = size
    data = json.dumps(payload).encode("utf-8")
    headers = _auth_headers({"Content-Type": "application/json"})
    return _post(BASE_URL + "/images/generations", data, headers)


def img2img(prompt, model, n, size, image_path):
    fields = {"model": model, "prompt": prompt, "n": str(n)}
    if size:
        fields["size"] = size
    body, ctype = _multipart(fields, {"image": image_path})
    headers = _auth_headers({"Content-Type": ctype})
    return _post(BASE_URL + "/images/edits", body, headers)


def _save_images(resp, out_dir, name_prefix):
    os.makedirs(out_dir, exist_ok=True)
    saved = []
    for i, item in enumerate(resp.get("data", [])):
        out_path = os.path.join(out_dir, f"{name_prefix}_{i}.png")
        b64 = item.get("b64_json")
        if b64:
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(b64))
            src = "b64_json"
        elif item.get("url"):
            with urllib.request.urlopen(item["url"], timeout=120) as r:
                blob = r.read()
            with open(out_path, "wb") as f:
                f.write(blob)
            src = "url"
        else:
            continue
        saved.append({"path": out_path.replace("\\", "/"),
                      "bytes": os.path.getsize(out_path), "source": src})
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", help="生成提示词")
    ap.add_argument("--image", help="参考图路径（给了就走 img2img/edits）")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--size", default=None)
    ap.add_argument("--out", default=os.path.join(HERE, "output"))
    ap.add_argument("--name", default=None)
    args = ap.parse_args()

    name_prefix = args.name or ("img_" + time.strftime("%Y%m%d_%H%M%S"))
    mode = "img2img" if args.image else "text2img"

    if args.image and not os.path.exists(args.image):
        print(f"ERROR: 参考图不存在: {args.image}")
        sys.exit(1)

    try:
        if args.image:
            resp = img2img(args.prompt, args.model, args.n, args.size, args.image)
        else:
            resp = text2img(args.prompt, args.model, args.n, args.size)
    except Exception as e:  # noqa: BLE001
        manifest = {"ok": False, "mode": mode, "model": args.model, "error": str(e)}
        with open(os.path.join(HERE, "_last.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"ERROR: {e}")
        sys.exit(1)

    saved = _save_images(resp, args.out, name_prefix)
    usage = resp.get("usage") or {}
    # 归一化 token 字段：images 端点用 input/output_tokens；兼容 chat 的 prompt/completion
    tokens = {
        "input": usage.get("input_tokens", usage.get("prompt_tokens")),
        "output": usage.get("output_tokens", usage.get("completion_tokens")),
        "total": usage.get("total_tokens"),
        "raw": usage,
    }

    manifest = {
        "ok": bool(saved),
        "mode": mode,
        "model": args.model,
        "prompt": args.prompt,
        "image_in": args.image,
        "size": args.size,
        "n": args.n,
        "images": saved,
        "tokens": tokens,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(HERE, "_last.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if saved:
        print(f"OK {mode} {args.model} -> {len(saved)} 张, "
              f"tokens total={tokens['total']}; 详情见 _last.json")
    else:
        print(f"ERROR: 接口返回无图。usage={usage}")
        sys.exit(1)


if __name__ == "__main__":
    main()
