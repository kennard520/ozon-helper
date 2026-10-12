---
name: ozon-help-sync
description: "重新抓取并更新 Ozon Global 卖家帮助中心的中文版全站，生成本地知识库（离线 HTML、Markdown、本地图片、全量索引）。站点是 Nuxt SPA 且反爬严格，正文数据必须经浏览器页面内 fetch 抓取。当用户要求「更新/重新拉取/同步 Ozon 帮助文档」、或要刷新本地 ozon-help-kb 知识库时使用。"
---

# Ozon Help Sync

把 Ozon 帮助中心（中文版，region=CHN）全站重新抓取为本地知识库 `E:\personal\ozon-helper\ozon-help-kb`。

## 工作流

按固定顺序执行，不要跳过或重排：

### 1. 抓取（Browser Use）

站点是 Nuxt SPA（页面 HTML 是空壳），内容由浏览器 JS 从内部 API 拉取，且 API 有反爬（直接 HTTP 请求会 307/403）。必须用浏览器页面内 `fetch(..., {credentials:'include'})` 递归抓取。完整步骤见 [references/fetch-workflow.md](references/fetch-workflow.md)。

产物：`raw\ozon_help_zh_raw.json`（含 `tree` + `docs`，docs 每篇有 `path/title/id/updated/breadcrumbs/contentJson`）。

### 2. 转换（scripts/convert.py）

把 raw JSON 转为离线 HTML（`html\`）+ Markdown（`markdown\`，带 frontmatter）+ `index.json` + 内联搜索索引。

```powershell
python "<skill>\scripts\convert.py"
```

### 3. 镜像图片（scripts/mirror_images.py）

下载文章内全部远程图片到 `html\images\`，并把 HTML/MD 里的远程 URL 替换为本地相对路径。

```powershell
python "<skill>\scripts\mirror_images.py"
```

### 4. 压缩图片（scripts/compress_images.py）

把 `html\images\` 中 >300KB 的 png/jpg 转成 WebP 并同步更新引用。

```powershell
python "<skill>\scripts\compress_images.py"
```

### 5. 校验（scripts/check_links.py）

核对 HTML/MD 引用的图片文件与 `html\images\` 一一对应，须输出「断链 0、孤儿 0」。

```powershell
python "<skill>\scripts\check_links.py"
```

全部完成后，用浏览器打开 `html\index.html` 抽查：目录树、文章页图片本地加载、搜索命中。

## 关键约束

- **四步顺序固定**：convert → mirror_images → compress_images → check_links。顺序错会导致 HTML 引用回退为远程 URL 或断链。
- 所有脚本路径硬编码指向 `E:\personal\ozon-helper\ozon-help-kb`；如目录迁移，先改脚本内路径常量。
- 反爬关键点：**不要用 curl/web_fetch 直接抓页面或 API**，必须在浏览器会话内 fetch（详见 references/fetch-workflow.md）。
- 环境：Windows 主机，用 PowerShell 工具运行脚本（无 Bash）。

## 已知限制

- 3 篇文章在源站正文为空（`/fulfillment/fbp/returns-`、`/fulfillment/fbp/rates`、`/fulfillment/fbp/supplies/product-availability`），转换后为占位页。
- 源站个别图片（如 `product-list.png`）可能下载失败，保留线上地址引用（check_links 会有 1 处远程引用，属预期）。
