# 设计：采集后自动发布到 Ozon（用户级开关）

- 日期：2026-06-20
- 状态：设计已确认，待写实现计划
- 影响范围：`ozon-listing-webui` 后端（`app_service`/`store`/`main`）+ 前端设置页；**插件无改动**

## 背景 / 问题

现状的流程是：插件采集 → 后端建草稿 + 自动映射属性 →（有媒体则插件后台传 OSS）→ 用户在 webui 编辑器里检查 → 手动点发布。

部分用户的工作方式是"采集完不在 webui 里改，直接发到 Ozon，到 Ozon 后台去改"。对他们来说 webui 这一步纯属多余。需要一个**用户级开关**：开了之后，采集生成草稿后自动接上发布，省掉手动点发布。

## 目标

- 加一个用户级配置 `auto_publish`（默认关），开启后采集即自动发布到 Ozon。
- 内容**原样直发**：采集到的俄语标题/描述 + 自动映射的属性，不跑 AI 优化（用户到 Ozon 改）。
- **best-effort**：发不出去（缺必填属性 / 类目没匹配 / 媒体未托管 / 余额不足）的草稿静默留在 webui 等人工，不打断采集、不抛错给插件。
- 与现有**媒体异步**正确配合：有媒体的草稿等媒体传完 OSS 再发（发布对 `media_status=pending` 是硬拦截的）。

## 非目标

- ❌ 自动发布里不跑 AI（已选原样直发）。
- ❌ 不做"逐次采集单独选发不发"——只做全局用户开关。
- ❌ 不做失败重试队列 / 通知中心——失败就留草稿。
- ❌ 不改插件——发不发由服务端读设置决定。
- ❌ 自动发布不豁免发布扣费——与手动发布走同一套 `publish_fee`。

## 配置项

新增用户级设置：

| key | 类型 | 默认 | 说明 |
|---|---|---|---|
| `auto_publish` | bool | `false` | 开启后采集生成草稿即自动发布到 Ozon |

- 存现有 `settings` 表（按 `user_id` 隔离），走现有 `get_settings` / `save_settings`，**无需建表/迁移**。
- 后端在采集 / 媒体回调里 `self.store.get_settings()` 读取。

## 触发点（与媒体异步的配合）

因为 `publish()` 对 `media_status=pending` 硬拦截，按草稿有无媒体分两条：

| 草稿情形 | 触发位置 | 时机 |
|---|---|---|
| **无媒体**（`media_status=done`） | `ext_collect_parsed` 里 `_auto_map_safe` 之后 | 采集完立即发 |
| **有媒体**（采集时置 `pending`） | `update_draft_media` 里媒体置 `done` 之后 | 插件后台把媒体传完 OSS 再发 |

新建草稿与重复采集（dedup）两条路径统一适用——两处触发点都覆盖到。

## 执行模型

### 后台线程

复用现有范式（`ai_video.py` 的 `threading.Thread`；`auto_map` 的 `contextvars.copy_context()` 把 `current_user_id` 带进子线程）：

- 触发时 `copy_context()` 捕获当前用户上下文，起一个 `threading.Thread` 跑 `publish(draft_id)`。
- 采集 / 媒体回调**立即返回**，不被 Ozon 那 ~20s 轮询阻塞（批量采集每个 SKU 各自后台发、互不阻塞）。
- `store` 自带 `RLock`，子线程读写 DB 安全。

### best-effort

- 后台 runner 整段 `try/except` 吞异常，只记日志，不影响采集。
- `publish()` 在校验失败 / 未配 OSS / 余额不足时本就返回 `{published: False}` 且把草稿标 `status='invalid'` + `validation_errors`，不抛异常；只有 Ozon 调用本身失败才抛 → 被 runner 吞掉。
- 草稿原样留在 webui，用户补齐后可手动发。

### 幂等防重发

守卫条件 = `auto_publish` 开 **且** 草稿 `status != 'published'`：

- 发布成功后 `publish()` 把 `status` 置 `published`，再次采集 / 媒体回调被守卫跳过 → **同一草稿最多自动发一次**。
- 重复采集（dedup）一个已发布草稿：`status` 仍是 `published`（dedup 不重置 status），守卫跳过，不会重发。
- **无需新增草稿字段**。

### 封装

抽一个 `self._maybe_auto_publish(draft_id)`：读设置 + 查 `status` 守卫 → 满足则派发后台线程。两个触发点各调一次。线程派发做成可注入/可 monkeypatch，方便测试同步断言。

## 前端

- 设置页加开关「采集后自动发布到 Ozon」+ 一行说明：「开启后采集会直接发到 Ozon，发不出去的留草稿等你手动补」。
- 走现有 settings 读写逻辑，无新接口。

## 错误处理 / 边界

- 后台发布抛错（Ozon 调用失败等）：runner 吞掉 + 日志，草稿不动。
- 校验失败 / 未配 OSS / 余额不足：`publish()` 已标 `invalid` 留草稿，不抛错。
- 有媒体但媒体补传一直没完成：永不进自动发布（守卫只在媒体 `done` 回调里触发），等用户手动处理——与现有"媒体未传完硬拦截发布"一致。
- 关开关后采集：永不自动发。
- 采集→媒体 done 之间用户把开关关掉：媒体 done 时重新读设置，已关则不发（符合预期）。

## 测试

- **后端**
  - 开关开 + 无媒体草稿 → 触发自动发布（断言 `_maybe_auto_publish` 派发 / publish 被调）。
  - 开关开 + 有媒体草稿 → 采集时**不**发；`update_draft_media` 媒体置 done 后才发。
  - 开关关 → 两条路径都不发。
  - 发布失败（校验不过 / Ozon 抛错）→ 不抛给采集调用方、草稿保留。
  - 已 `published` 的草稿 → 守卫跳过（幂等，不重发）。
- **前端**：设置页开关读写一条。
- **回归**：现有采集（`test_ext_bridge`）、发布、媒体异步、settings 测试不破。

## 部署 / 迁移

- 无 schema 变更（复用 `settings` 表）。
- 后端重建镜像 + 重启即可。
- **插件无改动**，用户无需刷新扩展。
