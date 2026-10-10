# F1d-3b 图片 tab AI 出图（图集计划）设计

**日期**：2026-06-27　**分支**：feat/auto-listing-ai-pipeline　**模块文档**：[material-gallery.md](../../product/material-gallery.md) + [workbench.md](../../product/workbench.md)

## 目标
图片 tab 第二期：AI 出图。让 AI 当"美术总监"设计图集方案(白底主图/细节俄化/场景/卖点信息图等槽位)，按槽生成图，生成图直接进图集(F1d-3a 图集区自动显示)。

## 现状（复用既有后端，零后端改动）—— 含纠正
- `api.designImagePlan(id, target=10)` → POST `/api/drafts/{id}/design-image-plan`：LLM 据看图理解+源图设计 ~target 张方案，写 `source_raw.image_plan`，返回 `{ok, plan:[slot...], count, fallback}`。无 understanding 会自动先跑 understand；无 images 报错「先采集/生成图片」。
- `api.imagePlan(id, force)` → GET `/api/drafts/{id}/image-plan`：返回 `{ok, plan:[{...slot, status:'todo'|'applied', candidate_url}]}`。status 据 `slot_images[slot_id]` 的 url 是否仍在 `draft.images`(图集)判定。
- `api.generatePlanSlot(id, slotId)` → POST `/api/drafts/{id}/generate-plan-slot`：按槽 action+source_idx 生成 1 张图，**直接 INSERT draft_images(source=generated, in_gallery=1 进图集)** + 记 `slot_images[slot_id]`，返回 `{ok, slot_id, candidate, draft}`。**同步阻塞**(AI 生图约 10-30s)。
- 槽 slot 形状：`{slot_id, role, label, action(white|localize|scene|infographic), source_idx, heading, bullets, scene_hint, prompt, status, candidate_url}`。
- **纠正**：`_add_candidate` 方法名/「候选区」docstring 是历史遗留——实际生成图**直接进图集**、不进 `ai_image_candidates`。plan 驱动的出图**无候选阶段、无 apply/discard**。`ai_image_candidates`+applyCandidates/discardCandidates 是另一条 legacy 批量手工编辑流，本期不接。
- api.js 已有 designImagePlan/imagePlan/generatePlanSlot。

## 范围外
- legacy 批量手工编辑流(whiten/scene/regen → ai_image_candidates → applyCandidates)：本期不接（与图集计划是两套）。
- 单图手工重绘/俄化：后续按需。

## 架构（沿用 composable + 组件模式）
1. **`composables/useImagePlan.js`** — `useImagePlan(draftRef, { onChange })` →
   - `plan`(ref)、`loading`(设计/刷新)、`genState`(slot_id→bool 生成中)。
   - `loadPlan(force=false)`：`imagePlan` → plan（含 status）。
   - `designPlan(target=10)`：`designImagePlan` → 重设计 → loadPlan(true)。
   - `generateSlot(slotId)`：`generatePlanSlot` → 成功 onChange()(刷新 draft→图集出现新图) + loadPlan() 刷新 status。
   - `generateAll()`：对 status=todo 的槽顺序 generateSlot（串行，避免并发打爆生图接口）。
   - 派生 `todoCount`/`appliedCount`。
2. **`components/workbench/AiImagePanel.vue`** — 顶部「AI 设计图集」+「刷新计划」+「一键出全部(N)」按钮；槽位列表：每槽显示 label + action 徽章 + 状态(待做/已出图) + 「生成」/「重出」按钮(生成中转圈)。空计划提示「先点 AI 设计图集」。
3. **接入 ImagesTab**：AiImagePanel 放在最上面(设计→出图→流入下方图集)，`@changed="emit('saved')"` → DetailTabs `fm.load`。

## 交互
- 进 tab → 自动 loadPlan(若 image_plan 已存在则显示，否则空)。
- 「AI 设计图集」→ designPlan → 槽位列表出现(全 todo)。
- 每槽「生成」→ 转圈 → 完成 → 图进图集(下方 F1d-3a 图集区刷新出现) + 该槽变「已出图/重出」。
- 「一键出全部」→ 串行生成所有 todo 槽。
- 无图集图时设计会报错 → toast 提示先有图。

## 数据形状
| 名 | 形状 | 来源 |
|---|---|---|
| slot | `{slot_id,role,label,action,source_idx,heading,bullets,scene_hint,prompt,status,candidate_url}` | imagePlan |
| status | `'todo'｜'applied'` | imagePlan(slot_images∩images) |

## 测试（Vitest）
- useImagePlan：loadPlan 调 imagePlan 填 plan；designPlan 调 designImagePlan 后 loadPlan(true)；generateSlot 调 generatePlanSlot + onChange + 重 loadPlan；generateAll 仅对 todo 串行；genState 标记生成中。
- AiImagePanel：渲槽位列表 + 状态徽章；「生成」触发 generateSlot；「AI 设计图集」触发 designPlan；空计划提示。
- gating：前端失败数 ≤32 基线不新增；新增用例全过。
