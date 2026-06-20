# 设计：采集性能优化 v2（媒体后台异步 + 原产国写死 + 并发）

- 日期：2026-06-20
- 状态：设计已确认，待写实现计划
- 影响范围：`ozon-seller-helper-ext`（插件）+ `ozon-listing-webui` 后端 + `drafts` 数据模型

## 背景 / 问题

采集慢有两个卡点，都压在采集的**同步流程**里：
1. **媒体下载传 OSS**：插件里下载 30 张图 + 视频再传 OSS，跨境下载大视频实测 **38 秒**；
2. **属性映射**：后端把俄文文本映射成 Ozon 数字 ID，首次 ~4s、重复 ~2s。

对比参考插件（卖家国度）：它采集只抓页面数据、把媒体/映射/上品的重活全交给它的后端（bcserp.com），所以插件端秒回。我们要在**不动后端架构、不下发 Ozon key、不降安全、不增加后端负担**的前提下追平它的采集速度。

关键事实（已查证）：
- 媒体的字节流**从不经过我们后端**——插件下载、直传 OSS，后端只发 presign（极轻）；
- 官方 Seller API 从国内服务器调用是行业常态，**不因 IP 风控**，无需把 key 下发前端；
- 竞品页的属性只有文本、没有 Ozon 内部 ID，**映射必须有人做**，省不掉，只能优化时机/并发。

## 目标

- 采集**秒回**（2~3 秒：只建草稿 + 映射属性，不等媒体）；
- 媒体在**插件 Service Worker 后台**异步并发传 OSS（不占后端、不阻塞采集）；
- 可靠：浏览器关闭中断后能**补传**，最终一致；
- 合规：媒体没传完 OSS **不让发布**（杜绝用 `ir.ozone.ru` 别人店铺链接发布）。

## 非目标

- 不下发 Ozon `Client-Id`/`Api-Key` 到前端（安全）；
- 不把媒体下载/上传/发布搬到后端（服务器资源有限）；
- 不改“所有属性都映射”——保持全量映射，不只映射必填。

## Part 1 — 属性映射优化（后端，小改）

1. **原产国一律“中国”**：`auto_map_attributes` 在**类目属性表（meta）**里查找原产国属性（属性名含 `Страна`，即俄文“国家/制造国”）。**不管竞品采到什么值、甚至竞品根本没采到这个属性**，只要类目有该属性，就把值设成 `Китай`（中国）、映射出对应字典值 ID 填入。即原产国强制中国，与采集到的内容完全无关。业务正确：跨境一律从中国发货。
2. **所有属性都映射**：保持现状，不缩减为只映射必填。
3. **并发加大**：`_resolve_pairs_concurrent` 的 `ThreadPoolExecutor` 上限从 `min(8, n)` 提到 `min(16, n)`。
4. **品牌**：已写死“无品牌”，不动。

## Part 2 — 媒体插件后台异步

### 数据流

```
点采集
 → 插件推数据（data 里图片/视频是 Ozon 原 URL）
 → 后端 ext_collect_parsed：建草稿（images=原URL）+ 映射属性 + 置 media_status=pending（有媒体时）
 → 返回草稿 id → 采集秒回、开编辑器 ✅
      ↓ 插件 background Service Worker（后台）
   并发下载媒体 → 直传 OSS → 调 update-draft-media（草稿 id, {原URL→OSS URL}）
      ↓ 后端
   把草稿 images/video_url 的原 URL 换成 OSS URL + 置 media_status=done
```

### 改动点

- **插件 `common/collect-flow.js`**：采集流程**去掉同步 `_rehostMedia`**；`collectParsed` 直接带 Ozon 原 URL 推送；拿到草稿 id 后**触发一次后台 rehost**（不等待）。
- **插件 `background.js`**：
  - 后台 rehost 任务复用现有 `uploadMediaOss`（并发 workers），传完调 `update-draft-media`；
  - 媒体下载/上传超时维持现状（宁慢勿失败）。
- **后端 `app_service` / `main`**：
  - `ext_collect_parsed`：建草稿时，若 `data` 含媒体 URL → `media_status='pending'`，否则 `'done'`；**不再依赖插件先传完媒体**；
  - 新接口 `POST /api/ext/update-draft-media`（需 JWT）：入参 `{draft_id, media_map: {原URL: OSS URL}}`；把草稿 `images`/`video_url` 中命中的原 URL 替换成 OSS URL，置 `media_status='done'`；
  - 新接口 `GET /api/ext/pending-media-drafts`（需 JWT）：返回当前用户 `media_status='pending'` 的草稿列表（`id` + 仍是原 URL 的 `images`/`video_url`），供插件补传。

## Part 3 — 补传 + 合规

### 补传（权威源 = 后端的 pending 草稿）

插件 `background` 在这些时机扫描补传：
- **采集成功后立即**触发一次（不等定时）；
- **Service Worker `onStartup`**（浏览器启动）；
- **打开编辑器时**；
- **定时周期扫描**：用 `chrome.alarms` 每 3 分钟扫一次。

扫描逻辑：`GET /api/ext/pending-media-drafts` → 对每个草稿，按其原 URL 下载媒体 → 传 OSS → `update-draft-media`。补传以后端 pending 列表为准，天然幂等（传完即 `done`，不会重复）。

### 合规（硬拦截发布）

发布前检查 `media_status`：
- `done` → 允许发布；
- `pending` → **拒绝**，提示“图片还在上传，请稍候再发布”。

检查同时落在**后端发布入口**（权威，前端绕不过）和**前端发布按钮**（即时提示，UX）。

## 数据模型

`drafts` 表新增一列：

| 列 | 类型 | 说明 |
|---|---|---|
| `media_status` | `TEXT`/`VARCHAR(16)` NOT NULL DEFAULT `'done'` | `pending`=媒体待传 OSS；`done`=无媒体或已传完 |

迁移：MySQL `_ensure_mysql_column` 探测补列、SQLite `_ensure_column`；**现有草稿默认 `done`**，不受影响、不会被误拦发布。

## 错误处理 / 边界

- 媒体下载/上传单张失败：该张保留原 URL（best-effort），但只要还有 `pending` 项，`media_status` 不置 `done` → 仍会被补传重试；
- 全部传成功才置 `done`；
- 无媒体的草稿（如无图商品）：建草稿即 `done`，不进补传、不挡发布；
- `update-draft-media` 只替换“命中原 URL”的项，避免覆盖用户在编辑器里手动改过的图。

## 测试

- **属性**：原产国一律“中国”——竞品采到别的国家时被改成中国；**竞品没采到原产国、但类目有该属性时，也会主动填中国**；并发 16 解析结果正确；全属性映射不漏。
- **媒体异步**：`ext_collect_parsed` 有媒体 → `media_status=pending` 且 `images` 仍是原 URL、秒回；`update-draft-media` 把原 URL 换成 OSS + 置 `done`；`pending-media-drafts` 正确列出待补传。
- **补传**：pending 草稿被扫描到并补传成功后变 `done`；幂等（已 done 不再传）。
- **合规**：`media_status=pending` 时调发布被后端拒绝。
- **回归**：现有采集（`test_ext_bridge`）、发布、草稿测试不破。

## 部署 / 迁移

- `drafts.media_status` 容器启动自动补列（MySQL/SQLite 双方言）；
- 后端重建镜像 + 重启；
- 插件改动需用户**刷新扩展**才生效（这次确实改了插件代码）。
