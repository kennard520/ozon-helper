# 自动上架流水线 — 流程 & AI/API 调用详情

> 2026-06-22 整理。承接 `2026-06-20-auto-publish-design.md`，补全"复制判定 + 原创图管线 + AI 调用细节"。
> 原则：**合规自动化**，不做"改图绕检测"。来源 Ozon / WB / 1688 同一套，"官方复制"只对 Ozon 有效。

---

## 1. 端到端流程

```
Ozon 链接 ─┐
WB   链接 ─┤→ 各来源采集适配器 → 归一成统一中间结构 draft(参数 + 图片 + 卖点)
1688 链接 ─┘                              │
                          ┌───────────────┴─ 来源 == Ozon ?
                          │  是 → 试 POST /v1/product/import-by-sku
                          │        ├─ 可复制 → 官方复制建卡 → 轮询 import/info → 完成 ✅
                          │        └─ 不可复制(unmatched / copying prohibited) ─┐
                          │  否(WB / 1688) ─────────────────────────────────────┤
                          └─────────────────────────────────────────────────────┴→
                                          【原创建卡分支 · 与来源无关 · 一份代码】
                                                   │
                                          ① AI 文案：俄语标题/属性/描述/标签 全 rewrite + 随机货号
                                                   │
                                          ② AI 图片管线：抠图 → 白底主图 → 场景图 → 俄语信息图 → 副图水印
                                                   │
                                             【人工确认】价格 / 货号 / 图文
                                                   │
                                          OSS 拿直链 → POST /v3/product/import → 轮询 import/info
```

**关键架构：原创建卡分支 source-agnostic（来源无关）。** 三个来源**唯一的差异在最上游的采集适配器**（Ozon 页 / WB 页 / 1688 offer 各自解析）；一旦归一成 `draft`，「Ozon 不可复制 / WB / 1688」走**完全同一条代码路径**，不是三套。
- 「官方复制」是 Ozon 独有的**捷径**；走不通就**降级**回这条共享主干。
- 输入小差异（不影响分支）：Ozon 不可复制可顺带复用源卡的 Ozon 类目作建卡提示；WB / 1688 需走 Ozon「建议类目」定类目。目标平台恒为 Ozon（`/v3/product/import`）。
- 全程慢操作（出图、抠图、Ozon 异步导入）走 `drafts.media_status` 异步任务，接口立即返 id，前端轮询。
- 人工确认：复制分支放在"试导入前"（import-by-sku 试即建）；原创分支放在"上传前"。

---

## 2. AI / 外部调用详情

### 2.1 Ozon Seller API
`https://api-seller.ozon.ru` ｜ 头：`Client-Id` + `Api-Key` + `Content-Type: application/json` ｜ 全 POST ｜ 客户端：`backend/ozon_client_adapter.py` 的 `post()`

| 接口 | 用途 | 关键入参 | 关键返回 | 状态 |
|---|---|---|---|---|
| `/v3/product/info/list` | 取源/竞品信息（名/价/类目/图） | `sku[]`/`offer_id[]`/`product_id[]` | `items[]`:sku,offer_id,description_category_id,price,images,barcodes | ✅ 已有 |
| `/v1/product/import-by-sku` | **官方复制**已有卡片 | `items[]{sku, offer_id, name, price, old_price, currency_code, vat}` | `result.task_id` + `unmatched_sku_list[]` | 🆕 待建 |
| `/v1/product/import/info` | 轮询导入结果（复制&原创共用） | `{task_id}` | `result.items[]{offer_id,product_id,status,errors[]}` status=imported/moderating/failed | ♻️ 有现成模式 (app_service.py:710-737) |
| `/v3/product/import` | **原创建卡**/更新 | `items[]{offer_id, description_category_id, type_id, attributes[], images[], price, 尺寸重量...}` ≤100/次 | `result.task_id` | ✅ 已有 |
| `/v1/description-category/tree` | 取类目+type_id（只能在末级建品） | `language` | `description_category_id, type_id, children[], disabled` | ✅ 已有 |
| `/v1/description-category/attribute` | 取类目属性表 | `description_category_id, type_id` | `id, name, is_required, dictionary_id, is_aspect` | ✅ 已有 |
| `/v1/description-category/attribute/values(/search)` | 取字典值 id | `attribute_id, description_category_id, type_id` | `result[]{id, value}` → 填 dictionary_value_id | ✅ 已有 |
| `/v4/product/info/limit` | 每日建卡额度，超额前拦截 | — | daily_create/daily_update/total {limit,usage,reset_at} | 🆕 建议加 |

**判定可复制（无预检布尔接口）**：调 import-by-sku → SKU 落 `unmatched_sku_list` 或 import/info 的 `errors[]` 报 copying prohibited = 不可复制 → 转原创。
**注意**：currency_code 要与后台币种一致；改 `brand` → 独立新卡，不改可能并入原 PDP（成跟卖）。

### 2.2 AI 文案（详细）

端点 `/v1/chat/completions`（Agnes 网关）｜ 实现 `backend/ai_card.py`（**已大半建成**）｜ 每商品约 **3 次** chat 调用。

**前置**：定 Ozon 类目 + type_id（建议类目 nav）→ `/v1/description-category/attribute` 取属性表（id/name/required/hint/字典）→ `build_profile()` 把源数据拼成 profile 喂 AI。

**调用 1 — 标题 / 描述 / 标签**（`_SYS_TITLE` → JSON `{ozon_title, description, hashtags[]}`）✅ 已有

| 产出 | Ozon 落点 | 规则（已写进 prompt） |
|---|---|---|
| `ozon_title` 标题 | `name` | 全新 **rewrite**，不照搬原标题；类目+卖点；**禁含品牌/厂商/商标**（generic） |
| `description` 描述 | 描述字段 | 俄语 **80–250 词**，流畅，不杜撰 |
| `hashtags` 标签 | 属性 **id 23171**(#Хештеги) | ≤30 个，每个 `#` 开头，多词用 `_` 连；无品牌/参数/品名，只 trend/style/theme |

**调用 2 — 属性 + 尺寸重量**（`_SYS_ATTRS` → JSON `{attributes:[{id,value}], weight_g, length_cm, width_cm, height_cm}`）✅ 已有

- 按类目属性表逐项填，1688 中文参数 → 俄语值（颜色/产地/型号/材质/功率…）；按每属性 hint/格式（频率区间 `100-200`、数值纯数字）；**Аннотация（短描述/营销描述）** 也在此作为属性填；未知不杜撰、省略。
- `assemble_attributes()` 把 `[{id,value}]` 解析成上架 `[{id,values}]`；字典属性用 `resolve_values`(→ `/v1/description-category/attribute/values/search`) 查 `dictionary_value_id`；查不到进 `unmapped` 让**人工补**，不瞎填。
- 尺寸重量单位换算（kg→g、mm→cm）；找不到给 0。
- 品牌默认 `Нет бренда`（generic，合规且独立卡）。

**调用 3 — 富文本 Rich-контент 文本【🆕 待新增，当前缺口】**

- 现状：`ai_card.py` 出标题/描述/标签/属性，但**不生成富文本**，需补。
- AI 出结构化文本块 JSON：`{blocks:[{heading, text, img_slot}]}`（俄语、rewrite，每块对应一张图位）。
- 代码把 blocks + **图片管线产出的图 URL** 组装成 **Ozon Rich-контент JSON**（widgets: raShowcase/raText/raColumns…），填到富文本属性（**Rich-контент JSON 属性，id 经 `/v1/description-category/attribute` 动态确认，常见 11254**）。
- **图链约束（2026-06-22 已核实，更正早前错判）**：富文本图**可以直接用 OSS 公网直链**，**不需要** Ozon CDN。Ozon 官方接受外部直链并在导入时自动抓取转存到自己 CDN（同主图）。要求：URL 以 `.jpg/.jpeg/.png` 结尾、**公网可达无需鉴权、无签名/不过期**、≤10MB/≤16MP；禁 Yandex.Disk/wampi.ru。你的 OSS(公共读+无签名+MD5永久key+.jpg)全合规，`rewrite_item_media` 发 OSS 直链就是对的。**坑**：① 别用带签名/有效期的 URL；② Ozon 异步抓取，抓完转存前别删 OSS 源图；③ 每图配俄语 alt 兜底。→ 富文本和主图同一条路，无需"发布后取回 cdn 链接"的绕。

**其它**：货号 `offer_id` **本地随机生成（非 AI）**；（可选）若类目有独立「Ключевые слова」SEO 词属性，可再加一项，与 #Хештеги 区分。

**合规红线（已在 prompt 内）**：全 rewrite 非直译；标题/标签禁品牌；描述不杜撰；属性查不到留空让人工补。

### 2.3 图片 AI（gen-image 中转站）
基址 `GPTPLUS5_BASE_URL`(默认 `https://az.gptplus5.com/v1`) ｜ model `GPTPLUS5_IMAGE_MODEL` ｜ 待建 `backend/gen_image.py`（移植 `generate.py`，**纯 urllib，零新依赖**）

| 调用 | 端点 | 用途 | 关键 params |
|---|---|---|---|
| edit | `/images/edits` (multipart, 字段 `image`，可加 `mask`) | **抠图**(`background=transparent,format=png`) / 白底主图 / 场景图 | model,prompt,image,size=1024x1536,background,format,quality,n |
| create | `/images/generations` (JSON) | 纯创建原创背景（少用） | model,prompt,size,background |

- 返回 `data[].b64_json` 或 `data[].url`。
- **省钱关键**：1 次 `edit` 抠出透明 PNG → PIL 复用到所有 10 张，模型只在要真实场景时再调。10 张图约 1~3 次模型调用。
- **待验**：中转站是否支持 `background=transparent` 出真透明；不支持→出纯白底再 PIL 抠白。

### 2.4 图片本地处理（PIL/Pillow，非 AI）
**唯一新增依赖 `pillow`**。负责：透明图合成到白底/模板、俄语信息图排版（Montserrat 字体随镜像走）、副图水印。模型不写俄文/数字（SKILL 硬规则）。

---

## 3. 图片管线（产出 10 张）

| # | 图类型 | 用什么 | 水印 |
|---|---|---|---|
| 0 | 抠图(透明 PNG，中间产物) | gen-image edit `background=transparent` | — |
| 1 | 白底主图 #FFFFFF 3:4 居中~12%边 | PIL 合成 透明图(或 model 直接出白底) | **❌ 主图禁水印/文字** |
| 2-3 | 多角度/细节 | PIL 合成 / gen-image edit | ✅ |
| 4 | 尺寸图底图 | PIL（数字俄文 PIL 加） | ✅ |
| 5-7 | 场景/安装/功能 | gen-image edit(产品当参考) | ✅ |
| 8-9 | 卖点/营销信息图 | PIL 排版(Montserrat) | ✅ |

**Ozon 图片硬要求**：每商品 ≤15 张（用 `primary_image` 时 images[] ≤14）；JPG/PNG；长边 200–7680；传**公网 OSS 直链**（`oss.py`）；主图干净无促销文字。

---

## 4. 服务端落地

| 能力 | 现状 |
|---|---|
| 出图 | ♻️ 移植 `generate.py` → `backend/gen_image.py`（stdlib） |
| 异步任务/轮询 | ✅ 现成模式（agnes 视频、Ozon import 都是 task_id→status） |
| 异步媒体 | ✅ `drafts.media_status`(pending/done) + `media.py` |
| OSS 直链 | ✅ `oss.py` |
| 翻译 | ✅ `translate.py`/`agnes.py` |
| Ozon 建卡+轮询 | ✅ `app_service.py` |
| **新增依赖** | 仅 `pillow` |

**Docker/服务器（国内网络）注意**：① 去掉了 rembg → 无模型下载坑；② `GPTPLUS5_*` env 进容器；③ Montserrat `.ttf` 进仓库/镜像，路径写死；④ 抠图/出图慢 → 挂 `media_status` 异步，别阻塞请求；⑤ 出图并发限 1~2。

---

## 5. 合规红线（固化）

1. 官方复制**尊重源卡"禁止复制内容"开关**——被拒就转原创，不绕。
2. 原创图**只留产品本体**：抠图天然去掉别人背景/水印，**不做"擦别人水印"功能**。
3. **主图无水印/无文字**；店铺水印只加副图。
4. 文案**全 rewrite**；货号随机；改 brand 独立卡。
5. 干净底图优先用**供应商授权的无水印图**。

---

## 6. 待建清单 & 顺序

1. `import_by_sku()` + 轮询（套 app_service 现有 import 模式）— 最快见效。
2. `backend/gen_image.py`（移植 generate.py）+ 抠图函数，实测验"透明能不能出"。
3. `backend/image_pipeline.py`：抠图→主图→场景→俄语信息图→水印→OSS→回填 `draft.images[]`，状态走 media_status。
4. 文案 rewrite：复用 translate/ai_card。
5. 前端：人工确认页（价格/货号/图文）。

## 7. 待核实

① 各接口精确 RPS；② Ozon 图片最小分辨率；③ 强管控类目原创建卡是否需额外资质；④ 中转站 `background=transparent` 支持度。
官方文档原文存 `ozon-listing-webui/outputs/`。
