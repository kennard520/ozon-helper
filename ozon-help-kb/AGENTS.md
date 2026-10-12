# Ozon 帮助中心知识库（中文版）—— 供 AI 工具使用

本目录是 Ozon Global 卖家帮助中心中文版（region=CHN）的**离线知识库**，共 267 篇文章，完整覆盖 18 个顶级分类。**目标用途：作为 AI 工具（豆包客户端、Codex 等）的上下文/知识来源，回答卖家关于 Ozon 平台规则的任何问题。**

## 目录结构

```
ozon-help-kb/
├── index.json        # 全量索引：文档树 + 文章清单（path/title/id/updated/url）
├── markdown/         # 267 篇正文，每篇一个 .md，带 YAML frontmatter（推荐读取）
├── html/             # 340 个离线网页（html/index.html 为浏览入口，含目录树+搜索）
├── raw/              # 原始抓取数据 ozon_help_zh_raw.json
└── tools/            # 转换/镜像/压缩/校验脚本
```

## 如何定位与读取文章

- **定位**：用 `index.json` 的 `tree`（章节树）和 `articles[]`（文章清单）按标题/路径定位任意文章。
- **读取**：文章正文在 `markdown/<文章路径>.md`（frontmatter 含 `title/path/id/updated/source`）。回答卖家问题时，先按语义/关键词在 `markdown/` 中检索相关文章，再读取正文作答，并引用来源路径。
- **离线浏览**：`html/index.html` 供人类浏览（无需代码）。

## 更新方式

需要刷新文档时，使用 `ozon-help-sync` skill：浏览器会话内抓取全站 → `convert.py` → `mirror_images.py` → `compress_images.py` → `check_links.py`（顺序固定）。

## 已知限制

- 3 篇文章源站正文为空（`/fulfillment/fbp/returns-`、`/fulfillment/fbp/rates`、`/fulfillment/fbp/supplies/product-availability`），为占位页。
- 文中内链指向线上原文；回答时优先用本地 `markdown/` 内容。
