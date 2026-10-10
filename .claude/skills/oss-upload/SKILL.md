---
name: oss-upload
description: 把本地图片或远程图片 URL 上传到阿里云 OSS，拿公网直链（用 ozon-listing-webui 里已配好的 OSS 凭证）。内容 MD5 去重。常用于把 AI 生成图/采集图转成 Ozon 能抓取的公网图。触发：/oss-upload、"上传到oss""传到阿里云""把图转成公网链接""rehost 图片"等。
---

# oss-upload — 阿里云 OSS 上传 Skill

## 用途

把图片传到阿里云 OSS 拿**公网直链**。典型用途：
- 把 `gen-image` 生成的图、或采集到的本地/竞品图，转成 Ozon 能抓取的公网 URL
- 内容 MD5 当对象 key，**自动去重**（同图不重复传）

## 凭证来源（复用已有配置）

- 直接读 `tools/ozon-listing-webui/data/products.db` 的 `settings` 表（`oss_*` 全局键，user_id=0）——**就是 webui 设置页里配好的那套**，无需再填。
- 复用 `tools/ozon-listing-webui/backend/oss.py` 的 `OssClient`（与发布 rehost 链路完全一致：`ozon-media/<md5>.<ext>` 命名、幂等去重）。
- 依赖 `oss2`（本机已装 2.19.1）。

## 执行步骤

### Step 1: 跑脚本

| 意图 | 命令 |
|---|---|
| 传本地文件 | `python .claude/skills/oss-upload/upload.py a.png b.jpg` |
| 传远程 URL | `python .claude/skills/oss-upload/upload.py https://x.com/img.png` |
| 通配批量 | `python .claude/skills/oss-upload/upload.py --glob "某目录/*.png"` |
| 传 gen-image 刚出的图 | `python .claude/skills/oss-upload/upload.py --from-genimage` |

Windows 下先 `$env:PYTHONIOENCODING="utf-8"`。

### Step 2: Read `_last.json`

结构：`uploaded`/`total` + `results[]`（每项 `input` / `url` 公网直链 / `key` / `dedup`(是否已存在去重) / `ok`）。

### Step 3: 把公网 URL 给用户

逐个列出 `input → url`；标出哪些是去重命中（`dedup=true`）。

## 与 gen-image 串联

出图 → 上传一条龙：
```powershell
python .claude/skills/gen-image/generate.py "提示词" --name 主图
python .claude/skills/oss-upload/upload.py --from-genimage
```

## 注意

- 远程 URL 会先下载再转存 OSS；已在 OSS 上的链接原样返回（不重复传）。
- `public_base` 留空时用默认 bucket 域名 `https://<bucket>.<endpoint>`；配了 CDN 自定义域名则用它。
- 这是**对外写操作**（公开可访问的对象）。批量传前确认要传的就是这些图。
- bucket 已设公共读；传上去即公开可访问，别传隐私/带敏感信息的图。
- `_last.json` 是产物，勿提交（已在本目录 `.gitignore` 忽略）。
