# F1d-2 特征(Attributes)tab 设计

**日期**：2026-06-27　**分支**：feat/auto-listing-ai-pipeline　**模块文档**：[docs/product/workbench.md](../../product/workbench.md)

## 目标
工作台中栏 DetailTabs 的「特征」tab：按当前变体所选 Ozon 类目，展示并填写类目属性（变体维度/必填/可选），支持字典下拉（单/多选 + 大字典远程搜）、自由文本、一键 AI 填充、必填缺失提示。替代 legacy `DraftDetail.vue` 的属性段（god-component 双真相源写法）。

## 现状（复用既有后端，零后端改动）
- `api.requiredCheck(id, lang)` → `{aspects, required, optional, missing, errors}`。每个 def：`{id, name, is_required, is_collection, max_value_count, is_aspect, dictionary_id, description, group_name, ...}`。后端**已排除**品牌(85)/原产国/「类型」属性。
- `api.attributeOptions(cat,type,attr,lang)` → `{values:[{id,value}], oversized}`（全量字典选项；>2000 项 `oversized=true`）。
- `api.attributeValues(cat,type,attr,q,lang)` → `{result:[{id,value}]}`（大字典实时模糊搜）。
- `api.aiFillAttributes(id)` → `{draft, mapped_count, error?}`（AI 直接写 `attributes_json`，**非** ai_proposal）。
- 当前值在 `draft.attributes` = `[{id, values:[{dictionary_value_id?, value}]}]`。
- 保存：`api.patchDraft(id, { attributes: [...] })`（merge，store 落 attributes_json）。

## 架构（消灭 god-component 双真相源）
legacy 的坏味：`attributesText`(JSON 字符串) + `attrInputs`/`attrOptions`/`attrOversized`/`attrLoading` 多个并行 map 当真相源；每次 pick → `save()` + `runRequiredCheck()`（每次都服务端往返算 missing）。

**新设计单一真相 + 客户端派生**（沿用 F1c approach A 哲学）：
- **单一真相**：`values` reactive map：`attrId → Array<{dictionary_value_id?, value}>`（即 Ozon 上架结构的单属性 values）。从 `draft.attributes` 构建。
- **defs 按类目拉一次**：`requiredCheck` 给分组（aspects/required/optional）；类目(category_id/type_id)变才重拉。
- **missing 客户端实时算**：`missingIds` = required（含 required 的 aspect）里 values 为空的 → 免每次往返。
- **save 防抖**：值变 → 300ms 防抖 `patchDraft({attributes})`；保存后 `emit('saved')` 让外层 `fm.load()` 刷新（草稿其它派生字段/流水线 attrs 步进度）。
- **options 懒加载**：打开某属性下拉才拉 `attributeOptions`；`oversized` 切远程搜 `attributeValues`。

## 组件边界
1. `composables/useAttributes.js`——`useAttributes(draftRef)` → `{ groups{aspects,required,optional}, values, missingIds, errors, loading, optionsOf, loadingOf, oversizedOf, ensureOptions(def), search(def,q), setValue(attrId, valuesArr), aiFill(), save(), reloadDefs() }`。owns 全部数据/逻辑。
2. `components/workbench/AttrField.vue`——纯展示单属性字段。props：`def`、`modelValue`(canonical values 数组)、`options`、`loading`、`oversized`、`missing`。按 `dictionary_id>0` 渲 `el-select`(multiple=is_collection，multiple-limit=max_value_count，filterable+clearable，oversized 时 remote)否则 `el-input`。change → 组装 canonical values 数组 emit `update:modelValue`；下拉打开 emit `ensure`；远程搜 emit `search`。required 缺失标红点。
3. `components/workbench/tabs/AttributesTab.vue`——布局：变体维度组（置顶，说明文字）/ 必填组（带 missing 计数 banner）/ 可选组（默认收起，展开切换）。顶部「AI 填充特征」按钮 + 「保存」按钮（值变已自动防抖存，按钮做兜底/即时存）。wires useAttributes。

## 交互
- 选变体 → tab 拉 defs + 用 draft.attributes 回填 → 渲三组。
- 字典属性：点开下拉懒加载选项；大字典输入≥2字远程搜；单/多选按 is_collection；选中即更新 values + 防抖存。
- 自由文本属性：输入 → values=`[{value:text}]` + 防抖存。
- AI 填充：点按钮 → `aiFillAttributes` → 用返回 draft 重建 values + 重算 missing；toast 提示 mapped_count / error。
- 缺必填：顶部 banner「还缺 N 项必填」+ 各缺失字段标红。
- 品牌：后端已排除，不在此 tab；如需提示可在必填组尾注「品牌在『商品信息』tab 填」。

## 数据形状
| 名 | 形状 | 来源 |
|---|---|---|
| def | `{id,name,is_required,is_collection,max_value_count,is_aspect,dictionary_id,description,group_name}` | requiredCheck |
| values（单属性） | `Array<{dictionary_value_id?, value}>` | draft.attributes / 用户填 |
| option | `{id, value}` | attributeOptions / attributeValues |
| 保存 patch | `{ attributes: [{id, values}] }` | setValue 聚合 |

## 测试（Vitest + @vue/test-utils）
- AttrField：dictionary_id>0 渲 el-select、否则 el-input；多选 is_collection；pick 后 emit canonical values；自由文本 emit `[{value}]`。
- useAttributes：从 draft.attributes 建 values；missingIds 算法（required 空→缺，填了→不缺）；setValue 后 save 发 `{attributes}`；aiFill 调 api 并重建。
- AttributesTab：渲三组、missing banner 计数、AI 按钮触发 aiFill。
- gating：前端失败数 ≤32 基线不新增；新增测试全过。

## 范围外（后续）
- AI **提案审阅**（ai_proposal_json 的 review/apply）= F1d-4，与本 tab 的「直接 AI 填充」不同。
- 图片 tab = F1d-3。
- 简介/主题标签(#hashtags 23171)：本期作为普通文本属性渲染即可，不特殊处理。
