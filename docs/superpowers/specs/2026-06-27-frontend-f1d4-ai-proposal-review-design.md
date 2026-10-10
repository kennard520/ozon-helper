# F1d-4 AI 提案审阅（ai_proposal）设计

**日期**：2026-06-27　**分支**：feat/auto-listing-ai-pipeline　**模块文档**：[workbench.md](../../product/workbench.md)

## 目标
工作台 DetailTabs 顶部加「AI 文案草案」审阅面板：对当前变体生成 AI 草案(标题/简介/标签/属性，含缺失必填)→ 逐项编辑/删除 → 应用到正式字段 或 放弃。补全 legacy 只渲 fields、漏渲 attributes 的缺口。这是前端重建的最后一块，做完删 DraftDetail god-component、legacy 路由下线。

## 现状（复用既有后端，零后端改动）
- `getDraft().draft.ai_proposal` = `{ts, fields:{ozon_title, description, category_id, type_id, category_path, brand_name, brand_id?, weight_g?, length_mm?, ...}, attributes:[{id, name, value, source('ai'|'missing'), required?}], annotation, keywords}` 或 `null`。
- 生成：`api.aiGenerate(id)`(完整：类目+文案+属性+品牌+尺寸) / `api.aiCopy(id)`(仅文案：标题/简介/标签)。返回 mode=draft(预览，写草案不自动应用) 或 mode=applied(若 ai_auto_apply)。
- 审阅：`api.aiProposalPatch(id, {op, key?, id?, value?})`，op ∈ edit_field/delete_field/edit_attr/delete_attr/discard → 返回 `{ok, proposal}`(discard 时 proposal=null)。
- 应用：`api.aiProposalApply(id)` → `{ok, draft, unmapped:[{id,name,value}]}`。fields 覆盖标量字段、attributes 解析(俄语翻译+查字典)合并进 attributes_json、清空草案。unmapped=值无法解析需手动补的项。
- 标签是 attribute id=23171（value 为标签串）；品牌 id=85 排除(走 fields.brand_name/brand_id)。

## 与其它 AI 的关系（独立三套）
- **ai_proposal**(本期)：全字段草案 + **用户审阅 apply** 工作流（最像传统草案）。流水线 copy 步是 aiGenerate**+自动 apply**(批量多变体)；本面板是**当前单变体的精细审阅**(生成→审→应用)，互补。
- F1d-2 `aiFillAttributes`：仅属性、直写无审阅。
- F1d-3b `designImagePlan`：仅图集、直写无审阅。

## 架构（沿用 composable + 组件 + emit('applied')→fm.load 模式）
1. **`composables/useProposal.js`** — `useProposal(draftRef, { onApplied })` →
   - `proposal`(ref，从 draft.ai_proposal 初始化，draftRef 变重置)；`hasProposal` computed。
   - 派生：`aiAttrs`(source='ai' 排除 id=23171)、`missingAttrs`(source='missing')、`tags`(id=23171 的 value)。
   - 编辑(调 aiProposalPatch → 用返回 proposal 更新本地)：`editField(key,value)`、`deleteField(key)`、`editAttr(id,value)`、`deleteAttr(id)`、`editTags(value)`(=editAttr(23171))。
   - `apply()` → aiProposalApply → `onApplied(r)`(r 含 draft+unmapped)。
   - `discard()` → aiProposalPatch discard → onApplied(无)。
   - `generate(mode)` → aiGenerate('full') / aiCopy('copy') → onApplied(刷新出新草案)。loading 状态。
2. **`components/workbench/ProposalPanel.vue`** — props draft、emit applied：
   - **空态**(无草案)：紧凑条「AI 文案草案」+「生成草案」(aiGenerate)/「快速文案」(aiCopy) 按钮。
   - **审阅态**(有草案)：头部「AI 待确认草案」+「应用到商品」/「放弃」/「重新生成」；
     - fields：俄语标题(input)、简介(textarea)、标签(input)。
     - AI 属性(aiAttrs)：每项 名+值 input + 删除。
     - 缺失必填(missingAttrs)：每项 名(标必填)+值 input 待补。
     - apply 后若 unmapped 非空 → toast「N 项未匹配字典，请手动确认」。
3. **接入 DetailTabs**：`<ProposalPanel :draft="fm.draft.value" @applied="onApplied" />` 放 STabs 之上。`onApplied` → `fm.load()` + `wb.reload()`(正式字段变、流水线 copy 进度刷新)。

## 交互
- 进变体 → 若有 ai_proposal 显审阅态、否则显空态生成按钮。
- 生成 → 出草案(标题/简介/标签/AI属性/缺失必填)。
- 逐项改/删 → patch 即时同步后端(本地 proposal 用返回值更新)。
- 应用 → 合并进正式字段(InfoTab/AttributesTab 随 fm.load 刷新) + 草案消失;unmapped 提示。
- 放弃 → 草案清空回空态。
- 无 AI key → 生成 400 → toast。

## 数据形状
| 名 | 形状 | 来源 |
|---|---|---|
| proposal | `{fields:{...}, attributes:[{id,name,value,source,required?}], ...}` | draft.ai_proposal |
| patch | `{op, key?, id?, value?}` | 编辑动作 |
| apply 返回 | `{ok, draft, unmapped:[{id,name,value}]}` | aiProposalApply |

## 测试（Vitest）
- useProposal：从 draft.ai_proposal 取 proposal；aiAttrs/missingAttrs/tags 派生；editField/editAttr/deleteAttr 调 aiProposalPatch(op 正确) 并用返回更新；apply 调 aiProposalApply + onApplied；discard 调 patch(discard)；generate 调 aiGenerate/aiCopy。
- ProposalPanel：无草案渲生成按钮+触发 aiGenerate；有草案渲标题/简介/AI属性/缺失项 + 应用触发 aiProposalApply + 放弃触发 discard。
- gating：前端失败数 ≤32 基线不新增。

## 收尾（F1d-4 完成后，单独跟进，不在本 plan）
- 删 `DraftDetail.vue` + `Collect.vue` god-component、退役 `/drafts-classic` 路由(F1 收口)。本 plan 只做 ProposalPanel；删除收口作为下一步确认后执行(涉及删大文件，先确认)。
