# Ozon 卖家帮助中心 · 本地知识库（中文）

将 Ozon Global 卖家帮助中心（https://global-help.ozon.com/zh）的**全部中文文章**离线保存到本地，形成可检索、可浏览、可入库（RAG）的知识库。

## 内容概况

| 项目 | 数值 |
|---|---|
| 顶级分类 | 18 |
| 文章总数 | 267 |
| 分类落地页 | 72 |
| 本地镜像图片 | 1194 张（大图已转 WebP 压缩） |
| 抓取时间 | 2026-10-11 |
| 地区/语言 | region=CHN · 简体中文 |
| 原始数据 | raw/ozon_help_zh_raw.json（7.9 MB，含文档树 + 全部正文 ProseMirror JSON） |
| 总体积 | 约 165 MB（HTML/MD/图片全部本地化，可离线使用） |

## 目录结构

```
ozon-help-kb/
├── README.md                  # 本说明
├── index.json                 # 全量索引（树结构 + 267 篇文章元数据）
├── raw/
│   └── ozon_help_zh_raw.json  # 原始抓取数据（可重跑转换）
├── markdown/                  # Markdown 版（适合检索 / RAG 入库 / 向量化）
│   └── <分类>/<子分类>/<文章>.md
├── html/                      # 离线网页版（双击 index.html 即可浏览）
│   ├── index.html             # 首页：分类卡片 + 完整目录树 + 站内搜索（Ctrl+K）
│   ├── assets/                # 样式与交互脚本
│   ├── images/                # 已镜像到本地的全部文章图片
│   └── <分类>/<子分类>/<文章>.html
└── tools/
    ├── convert.py             # ProseMirror JSON → HTML/Markdown 转换器
    ├── mirror_images.py       # 图片镜像脚本
    └── scan_nodes.py          # 节点类型扫描（开发用）
```

## 使用方式

- **离线浏览**：用浏览器打开 `html/index.html`。左侧是完整目录树（可展开/折叠），顶部搜索框支持全站文章标题/路径检索（快捷键 Ctrl+K）。所有页面、样式、图片均为本地文件，无网络依赖。
- **RAG / 检索**：`markdown/` 下每篇文章一个 `.md` 文件，带 YAML frontmatter（title / path / id / updated / source），正文为干净 Markdown，可直接用于向量化、全文检索或喂给大模型。
- **程序读取**：`index.json` 含完整树结构与文章清单（路径、标题、更新时间、线上 URL）。

## 重新生成

```bash
# 1. 修改 raw/ozon_help_zh_raw.json 后重新转换
python tools/convert.py

# 2. 重新镜像图片（默认已镜像，跳过已有文件）
python tools/mirror_images.py

# 3. 压缩大图并同步更新引用（可选，已默认执行）
python tools/compress_images.py
```

## 说明与限制

- 正文为 Ozon 文档系统（KMS）的 ProseMirror 结构化数据，转换器已覆盖全部节点类型（段落、标题、列表、表格、提示框、折叠、页签、图片、代码块、文件、地区分块、Iframe 等）。
- 3 篇文章（`/fulfillment/fbp/returns-`、`/fulfillment/fbp/rates`、`/fulfillment/fbp/supplies/product-availability`）在源站正文为空，已保留为占位页。
- 1 张图片（product-list.png）源站返回错误未能镜像，其引用保留线上地址。
- 文中内链（如“了解 OGL 服务详情”）指向线上原文地址；如需完全内网化，可另行改写为本地相对链接。
- 抓取仅保存公开帮助内容，未包含需要登录的 Seller 后台数据。

## 抓取方法（复现）

1. 站点为 Nuxt SPA，内容经 `https://global-help.ozon.com/document-manager-api/global-help/api/v3/...` 加载，带反爬 cookie 校验。
2. 流程：浏览器打开 `/zh?region=CHN` → 收集 18 个顶级分类 → 递归调用 `section/public/by-path` 得文档树（72 个分类）→ 对 267 篇文章调用 `document/public/by-path?lang=zh&childDocsRegion=CHN` 抓正文。
3. 导出为 JSON 后由 `tools/convert.py` 转换。
