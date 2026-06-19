#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""oss-upload skill：把本地图片 / 远程图片 URL 上传到阿里云 OSS，拿公网直链。

复用 ozon-listing-webui 的 OssClient（内容 MD5 当 key 幂等去重、ozon-media/ 前缀），
凭证从 tools/ozon-listing-webui/data/products.db 的 settings 表读（user_id=0 全局 oss_*），
即"用之前配好的那套"。

用法：
  python upload.py a.png b.jpg                 # 传本地文件
  python upload.py https://x.com/img.png       # 传远程 URL（下载后转存 OSS）
  python upload.py --glob "output/*.png"       # 按通配批量
  python upload.py --from-genimage             # 传 gen-image 最近一次产出的所有图

结果：每个输入 -> 公网 URL；清单写本目录 _last.json；stdout 打一行 OK/ERROR。
依赖：pip install oss2（本机已装 2.19.1）。
"""
import argparse
import glob as globmod
import hashlib
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
WEBUI = os.path.join(REPO, "tools", "ozon-listing-webui")
DB_PATH = os.path.join(WEBUI, "data", "products.db")
OUT_PATH = os.path.join(HERE, "_last.json")
GENIMAGE_MANIFEST = os.path.join(REPO, ".claude", "skills", "gen-image", "_last.json")

sys.path.insert(0, WEBUI)


def die(msg, code=1):
    print("ERROR: " + msg)
    try:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump({"ok": False, "error": msg}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    sys.exit(code)


def load_oss_settings():
    if not os.path.exists(DB_PATH):
        die(f"找不到 products.db（{DB_PATH}）。先在 ozon-listing-webui 设置页配阿里云 OSS。")
    con = sqlite3.connect(DB_PATH)
    try:
        rows = con.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'oss_%'"
        ).fetchall()
    finally:
        con.close()
    settings = {}
    for k, v in rows:
        try:
            dec = json.loads(v)  # settings.value 是 JSON 编码
        except Exception:
            dec = v
        settings[k] = dec
    return settings


def collect_inputs(args):
    items = list(args.inputs or [])
    for pat in args.glob or []:
        items.extend(sorted(globmod.glob(pat)))
    if args.from_genimage:
        if not os.path.exists(GENIMAGE_MANIFEST):
            die(f"找不到 gen-image 产出清单（{GENIMAGE_MANIFEST}）。先跑 gen-image 出图。")
        with open(GENIMAGE_MANIFEST, encoding="utf-8") as f:
            man = json.load(f)
        items.extend(img["path"] for img in man.get("images", []) if img.get("path"))
    # 去重保序
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*", help="本地文件路径 或 http(s) 图片 URL")
    ap.add_argument("--glob", action="append", help="通配批量，可多次")
    ap.add_argument("--from-genimage", action="store_true", help="传 gen-image 最近产出的图")
    args = ap.parse_args()

    inputs = collect_inputs(args)
    if not inputs:
        die("没有要上传的输入。给文件路径/URL，或用 --glob / --from-genimage。")

    from backend.oss import OssClient  # noqa: PLC0415

    client = OssClient(load_oss_settings())
    if not client.configured():
        die("OSS 未配置完整（endpoint/bucket/AccessKeyId/AccessKeySecret 缺一）。去设置页补。")

    results, ok = [], 0
    for src in inputs:
        rec = {"input": src}
        try:
            if src.lower().startswith(("http://", "https://")):
                url = client.upload_remote(src)
                rec.update(url=url, dedup=None)
            else:
                if not os.path.exists(src):
                    raise FileNotFoundError(f"本地文件不存在: {src}")
                with open(src, "rb") as fh:
                    data = fh.read()
                ext = os.path.splitext(src)[1].lstrip(".") or "jpg"
                key = f"ozon-media/{hashlib.md5(data).hexdigest()}.{ext}"
                existed = client.object_exists(key)
                url = client.upload_bytes(data, ext)
                rec.update(url=url, key=key, dedup=bool(existed),
                           bytes=len(data))
            rec["ok"] = True
            ok += 1
        except Exception as e:  # noqa: BLE001 - 单个失败不阻断整批
            rec.update(ok=False, error=str(e))
        results.append(rec)

    manifest = {"ok": ok == len(inputs), "uploaded": ok, "total": len(inputs),
                "results": results}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"OK 上传 {ok}/{len(inputs)} 个；详情见 _last.json")
    if ok != len(inputs):
        sys.exit(1)


if __name__ == "__main__":
    main()
