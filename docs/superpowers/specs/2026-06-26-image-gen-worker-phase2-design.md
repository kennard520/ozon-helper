# 阶段2：AI 出图 worker 化（RabbitMQ + 独立 worker）— 设计

日期：2026-06-26
状态：待用户评审
依赖：阶段1（`draft_images` 表）已上线。

## 目标

把「AI设计并生成10张图」从**前端同步循环**改成**后端异步 worker**：
收单→入队立即返回→worker 排队消费→**逐图**生成+传OSS+落库（`draft_images`，source=generated）→
每张图独立更新状态（per-image 粒度）→整组完成后更新任务成败（成功X/失败Y）。worker 并发可配。

## 组件

1. **主 app（API）**：提交任务、查任务状态。不再自己出图。
2. **RabbitMQ**：任务队列（durable）。同 docker 网络一个轻量容器（daocloud 镜像拉）。
3. **worker 服务**：**同一镜像、第二个容器**，entrypoint=`worker.py`；连 RabbitMQ + MySQL + OSS + AI 配置。

## 数据表

`gen_jobs`（任务级）：
- `id`、`draft_id`、`status`(queued/designing/running/done/failed)、`target`(目标张数)、
  `total`(设计出的张数)、`succeeded`、`failed`、`error`、`created_at`、`updated_at`。

`gen_job_images`（逐图生成跟踪）：
- `id`、`job_id`、`slot_id`、`label`、`status`(pending/running/done/failed)、`url`(成功后)、`error`、`updated_at`。
- 成功的图**同时**写一行 `draft_images`(source=generated)——`gen_job_images` 是出图过程跟踪，
  `draft_images` 是最终图片(阶段1 的规范表)。

## 流程（收单→worker 开干）

1. **提交** `POST /api/drafts/{id}/gen-images {target:10}`：
   - 建 `gen_jobs`(status=queued, target)；向 RabbitMQ 发一条消息 `{job_id, draft_id, target}`；**立即返回 job_id**。
   - 同一草稿已有进行中任务则拒绝(幂等，不重复出图)。
2. **worker 消费**一条 job 消息：
   - status→designing：复用 `design_image_plan`（看图理解缺则自动跑）设计 ~target 个槽位；
     为每个槽建 `gen_job_images`(pending)；写 `gen_jobs.total`。
   - status→running：**按可配并发**(env `GEN_CONCURRENCY`，默认4)并发处理各槽位，每张：
     - status→running → 生成图(`generate_plan_slot` 的出图逻辑) → **传 OSS 拿公网 URL** →
       INSERT `draft_images`(url, type, source=generated, position 末尾) →
       `gen_job_images`(status=done, url)。**每张完成即独立落库**(per-image 通知靠 DB 状态变更)。
     - 失败：**重试 3 次**(退避)；仍失败 → `gen_job_images`(status=failed, error)。
   - 全部槽位终态后：`gen_jobs`(status=done, succeeded=成功数, failed=失败数)。
   - **ack 消息**(处理完才 ack；worker 中途崩 → RabbitMQ 重投 → 重处理时跳过已 done 的槽，幂等)。
3. **查状态** `GET /api/gen-jobs/{job_id}`（或 `GET /api/drafts/{id}/gen-job/latest`）：
   返回 `{status, total, succeeded, failed, images:[{slot_id,label,status,url}]}`。前端轮询。

## 并发 / 队列语义

- **队列粒度=任务**(一条消息=一个出图任务)；**图粒度的并发在 worker 内部**(env 配置的并发池)。
  这样满足「worker 排队 + 并发可设 + 逐图通知」，又不必把单图拆成消息(省去二段式 design→fanout)。
- 多个任务排队：RabbitMQ 顺序投递，worker 一个个(或多 worker 各拿一个)消费。
- prefetch=1（一个 worker 一次只处理一个 job，job 内部再并发图）。

## OSS 上传

worker 生成的图字节 → 直接传 OSS（复用 app 现有 OSS 上传逻辑/凭证）→ 存公网 URL 进 `draft_images`。
（区别于阶段1 `_add_candidate` 存 /media 本地：worker 直接传 OSS，省掉后续 rehost。）

## 失败 / 重试 / 幂等（两层，分工明确）

RabbitMQ **没有自动 backoff 重试**，只有「未 ack / nack-requeue 就重投整条消息」。本设计一条消息=一整任务，
所以 MQ 重投是**任务级崩溃兜底**，替代不了**单图临时失败**——两层互补：

- **单图重试 3 次（操作级，保留）**：某张图临时失败(网关502等)→ 退避重试它，**不影响其余已出的图**。
  叠加 gen_image 网关级(429/5xx)重试。这是 MQ 给不了的细粒度。
- **RabbitMQ 重投（任务级崩溃兜底）**：worker 处理完(成功**或**已标记失败都算完)就 **ack**；只有 worker
  崩溃/没 ack 才重投整条消息 → 重处理时按 `gen_job_images.status` **跳过已 done 的槽**(幂等)，只补没出的。
- **不另写任务级重试代码**——那层交给 MQ 重投 + 幂等跳过。
- 整 job 彻底失败：status=failed + error，已成功的图保留在 `draft_images`(用户可见、可删)。

## worker 容器部署

- 同 `ozon-webui:latest` 镜像，`docker run ... ozon-webui:latest python -m backend.worker`（第二容器）。
- env：RabbitMQ 地址/凭证、`OZON_MYSQL_*`、OSS、AI 网关(同主 app 的 .env.run + MQ)。
- RabbitMQ 容器：`rabbitmq:3-management`(daocloud 镜像)，durable queue，账号密码，`--restart always`。
- 内存：RabbitMQ ~150MB + worker ~普通 Python；1.6GB 机器要盯着(MySQL+app+MQ+worker)，必要时给 worker 限并发。

## 前端（阶段3，单独 spec，这里只占位）

「AI设计并生成10张图」按钮 → 调提交接口拿 job_id → 轮询状态 → 进度条「生成 3/10…」+ 逐图状态 →
完成弹「成功X/失败Y」，新图已在图片列表(draft_images)里。

## 测试

- worker 流程单测（mock 出图/OSS）：设计→逐图 done/failed→job 成败计数；重投跳过已 done 幂等。
- 提交接口：建 job + 发消息(mock MQ)；重复提交拦截。
- 状态接口：返回 per-image 进度。
- 部署后线上：点出图 → 立即返回 → 轮询看到逐图进度 → 完成计数；worker 容器日志正常 ack。

## 已定（用户确认）

1. 队列粒度：**任务级消息 + worker 内部图并发**。
2. 状态接口：按 job_id + 按 draft 查最新 job，**两个都给**。
3. worker 默认并发：**4**（env `GEN_CONCURRENCY` 可调）。
4. 重试：单图重试3次保留；任务级靠 MQ 重投+幂等，不另写。
