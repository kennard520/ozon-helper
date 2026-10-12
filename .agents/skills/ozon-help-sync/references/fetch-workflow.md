# 抓取工作流（Browser Use）

目标：把 Ozon 帮助中心中文版（region=CHN）全站正文抓成 `raw\ozon_help_zh_raw.json`。

## 为什么必须用浏览器页面内 fetch

- 站点是 Nuxt SPA，`curl`/`web_fetch` 直接抓页面只得到空壳（`data-ssr="false"`）。
- 内部 API 有反爬：工具级 `bu.http_get` 或外部 HTTP 请求会触发 307 无限重定向 / 403。
- 只有**在已登录的浏览器页面里执行 `fetch(url, {credentials:'include'})`** 才带正确 cookie，能拿到数据。

## 步骤

用 `computer_use_tool`（plane="bu"，`import seed_browser_use as bu`）执行：

### 1. 打开站点

```python
bu.navigate("https://global-help.ozon.com/zh?region=CHN")
bu.wait_for_load(timeout=20)
```

### 2. 定位文档树

先取项目设置确认语言与地区：

```python
proj = bu.js('(async function(){ const r = await fetch("/document-manager-api/global-help/api/v3/project?language=zh", {credentials:"include"}); return JSON.stringify(await r.json()); })()')
```

递归抓章节树（相对路径，绕开域名级反爬）。`by-path` 返回的节点含 `articles[]` 和 `sections[]`：

```python
# 例：抓根级章节
r = bu.js('(async function(){ const resp = await fetch("/document-manager-api/global-help/api/v3/section/public/by-path?path=/&lang=zh&childDocsRegion=CHN", {credentials:"include"}); return JSON.stringify(await resp.json()); })()')
```

对每个 section 递归调用 `by-path?path=<章节路径>`，收集所有 `articles[]`（含其 `path`/`title`/`url`）和嵌套 sections，直到叶子。最终得到完整文档树。

### 3. 抓全部文章正文

对每篇文章调用：

```python
r = bu.js('(async function(){ const resp = await fetch("/document-manager-api/global-help/api/v3/document/public/by-path?path=<文章路径>&lang=zh&childDocsRegion=CHN", {credentials:"include"}); return JSON.stringify(await resp.json()); })()')
```

正文在返回值的 `contentJson` 字段（ProseMirror JSON）。

**分批并发**：分小批（每批 45~60 篇，批内并发 5），避免触发限流。用 `bu.js` 的 Promise.all 并发，并等待完成。

### 4. 组装并导出 raw JSON

在页面内把 `tree` + `docs`（每篇含 `path/title/id/updated/breadcrumbs/contentJson`）组装成：

```json
{ "fetchedAt": "...", "tree": [...], "docs": [...] }
```

用浏览器下载导出（页面内创建 Blob 并触发下载），保存为 `raw\ozon_help_zh_raw.json`，再复制到项目目录。

## 验证

- 文章数应约 267，顶级分类 18 个。
- 检查是否有空正文文章（记录其 path，转换后保留占位页）。
- 每篇应有非空 `contentJson`（除已知 3 篇源站本身为空）。

## 环境注意

- 若页面要求登录/验证，按 Browser Use 规则走 `interaction.request_action`（type="browserControl"）交接，不要强行绕过。
- 大 JSON 用浏览器下载而非页面变量，避免触发长度限制。
