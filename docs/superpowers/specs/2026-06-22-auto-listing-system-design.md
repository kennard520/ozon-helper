# Ozon 自动上架系统设计 v2（收敛版）

> 2026-06-22。把 `ozon-product-kit`/`gen-image` 两 skill 产品化进 `ozon-listing-webui` 服务端。
> 本文为权威基线，收敛此前所有讨论。

---

## 1. 需求

### 功能（两大路径）
- **复制路径（Ozon 且源卡允许复制）**：采集时直接 `import-by-sku` 到当前店 → 建卡完成。**不建可编辑草稿；要改去 Ozon 后台改。**
- **原创路径（Ozon 不可复制 / WB / 1688）**：采集 → draft → 理解 → 文案 → 图片 → 富文本 → (可选)视频 → 人工确认 → 发布。
  - 文案：俄语标题/简介(描述+营销)/标签/属性，**重写**（非直译、避查重、无品牌）。
  - 图片：**逐图可控**——每张可「俄化 / 重做 / 保留原样」；出图进候选区，用户挑保留。
  - 富文本：billboard 大图序列（文字烤图里），图链用 **OSS 直链**（已核实 Ozon 接受外链）。
  - 视频：**前端幻灯片(MP4)**，选图拼接、直传 OSS、服务器零压力；后端 AI 视频(Agnes)保留不动。

### 非功能
- **省**：多模态"理解"只跑一次并缓存；下游(文案/图片/属性)全复用文本，不重复读图。出图按用户勾选生成。
- **快/不压服务器**：慢操作异步(`media_status`)；视频在浏览器做、直传 OSS。
- **合规**：Ozon 图 25 条 + 禁止 15 条(搬 skill)；复制尊重"禁止复制"开关；原创避感知哈希查重。
- **全程人工可控**：每步可看、可改、可重做；AI 写的数字标"待核对"高亮。
- **来源无关**：Ozon/WB/1688 → 统一 `draft`。

### 约束
- 栈：FastAPI + SQLite(本地)/MySQL(服务器 OZON_MYSQL_*) + Vue3/Element + 阿里云 OSS + gpt-image 中转站(`GPTPLUS5_*`,模型 `gpt-image-2-2`) + Agnes。
- **复用现有**：drafts/settings(多店)/publish(OSS rehost + 属性 11254)/media_status/候选区(`start_image_batch`)/presign 上传/ai_card/copy_flow。
- 个人维护 → 简单优先、少加依赖。

---

## 2. 高层设计

### 核心原则
1. **草稿为中心**，来源无关。
2. **理解一次，处处复用**：一次**多模态**调用 → 结构化"理解"(事实+逐图角色+可信度+文案种子)缓存，文案/图片/属性全吃它，不重复读图。
3. **复制走捷径**：Ozon 可复制即复制、不建草稿；其余才进原创向导。
4. **逐图人工可控**：图片计划勾选→只做勾的→候选区挑保留；每张可俄化/重做/保留。
5. **图全 gpt-image-2-2 edit + 传源图**：保产品一致；俄语文字交 AI 渲染(**数字必 QC**)；不用 PIL。
6. **skill 即 spec**：prompt 模板/10图方案/类目模板/提取分级/合规/QC 直接搬。
7. **模型可配**：多模态/文本/生图/视频 四槽，admin 各填各。

### 组件图
```
采集(Ozon/WB/1688) ─┬─[Ozon&可复制]→ import-by-sku→当前店建卡 ✅(无草稿)
                    └─[其余]→ draft
                              │
        ┌──────── AppService ─┴───────────────────────────────────┐
        │ 理解层(多模态,1次,缓存)  生成层(逐图)        发布层(现成) │
        │ 看图+读字+理解→事实/角色 ├ 文案: 文本LLM       to_ozon_import│
        │ /可信度/文案种子         ├ 图片: gpt-image edit + 属性11254  │
        │                          ├ 富文本: billboard   + OSS改链     │
        │                          └ 视频: (前端)        publish       │
        └──────────┬───────────────┬──────────────────────┬──────────┘
          source_raw缓存      media_status异步        /v3/product/import
   外部AI: 多模态(理解) · 文本LLM(文案) · gpt-image-2-2(图) · Agnes(后端视频)
   前端: ffmpeg.wasm 幻灯片→presign→OSS直传(服务器只签名)
```

### 数据流
```
复制:   采集 → try import-by-sku(当前店) → 可复制?建卡完成 : 转原创
原创:   draft → 理解(多模态,缓存) → 文案 + 图片(逐图:俄化/重做/保留,候选区)
                → 富文本(billboard) → (可选)前端视频 → 人工确认 → 发布
```

---

## 3. 深入设计

### 3.1 数据模型（扩展 `draft.source_raw`，不动表）
```jsonc
source_raw: {
  images:[...], detail_images:[...], variant_group, variants,   // 现有
  understanding: {                         // 🆕 理解层缓存(跑一次)
    type, material, specs:{标签化}, points:[], scenes:[], kit:[], audience,
    images:[ {idx, role:整体|细节|卖点|尺寸|包装|场景} ],   // 逐图角色
    confidence:{ "<字段>": 用户确认|图片识别|合理推断|待确认 },
    copy_seed:{ title_kw:[], desc_points:[] }               // 文案种子
  },
  image_candidates:[ {url, from, status:候选|保留} ],         // 🆕 候选区(或复用现有)
  rich_content_json:{...}                                     // 现有(发布塞 11254)
}
```

### 3.2 模型配置（4 槽，admin 设置页）
`settings_migrate.migrate_ai` → `{ai_multimodal🆕, ai_text, ai_image, ai_video}`，各 `{engine, api_base, api_key, model}`。
| 槽 | 用途 | 取 |
|---|---|---|
| `ai_multimodal` 🆕 | 理解层(看图理解) | `ai_config(s,"multimodal")` |
| `ai_text` | 文案/翻译/属性 | 已有 |
| `ai_image` | 生图(engine: agnes/gptimage) | 已有 |
| `ai_video` | 后端 AI 视频 | 已有(保留) |

### 3.3 理解层（一次多模态，缓存）
```
输入(一次性全给): 标题 + 图(主图+详情,挑≤6张降分辨率) + 详情 + 描述 + 参数
   ↓ 多模态 LLM(ai_multimodal): 看图+读字+理解
输出: understanding{事实(标签化specs) + 逐图角色 + 4级可信度 + 文案种子}
   → 缓存 source_raw.understanding (已有则跳过)
```
- **解决"数字汤"**：LLM 看尺寸图直接懂"36=高"，不是裸数字；源参数当锚，数字标"待核对"。
- **角色标注顺手做**：LLM 看图直接标整体/卖点/尺寸…（不用启发式），供图片步"发对应源图"。
- (可选)关键参数图加阿里云 OCR 当"精确数字锚"喂给 LLM。
- **vision 只此一次**，下游全文本复用。

### 3.4 文案层（1 次文本 LLM，复用 understanding）
- 复用 `ai_card.generate_card` 思路，profile = understanding(非裸OCR)。一次出 `{标题, 简介(描述+营销), 标签, 信息图俄语要点}`。重写、无品牌。
- 跟卖/复制路径不到这；原创才调。属性单独一次(需类目表)。
- AI 写的数字 → 前端橙色高亮 + "待核对 N 项"。

### 3.5 图片层（逐图可控，全 gpt-image-2-2 edit + 传源图）
- **图片计划**(理解层产出)：列出每张(类型/用哪角色源图/俄语文字/预估token)，**逐条勾选**。
- **出图**：只做勾选的 → 进**候选区**。每张「保留/弃用/重做这张」。
- **源图**：每张「俄化(单张 edit 换中文→俄语)/保留原样/删」。
- **prompt**：skill 通用后缀 + 角色专属；文字图内嵌"render exactly: <俄语>，其它不写字"。
- **QC(必做)**：合规(无中文/水印/价格) + 产品一致 + **数字/拼写核对**；失败重试≤2。
- 最终 `draft.images` = 用户 curate 的混合(部分俄化 + 部分重做保留 + 部分原样)。
- **智能推荐**给默认勾选：营销拼图→默认"重做"；干净产品图→默认"俄化"。

### 3.6 富文本（billboard）
- 把挑定的图按序拼 `build_rich_content`(billboard, version 0.3) → `source_raw.rich_content_json`。
- 发布侧现成：`to_ozon_import_item` 塞属性 11254、`rewrite_item_media` 图链→OSS 直链。
- **图链 OSS 直链 OK**(已核实)：要求 .jpg/.png、公网无鉴权、无签名/不过期；抓取转存前别删源图。

### 3.7 视频（前端 MP4 幻灯片，服务器零压力）
```
选图(图片步挑好的) → 浏览器 ffmpeg.wasm 拼 MP4(停留+转场)
   → /api/media/presign(现成) → 浏览器直传 OSS → draft.video_url
```
- 服务器只签上传地址，不碰视频字节。
- 坑：OSS 需配 CORS(canvas 读图导出);确认 Ozon 视频格式/时长/尺寸/大小。
- 后端 AI 视频(`start_ai_video`/Agnes)**保留不动**，两者并存。

### 3.8 智能推荐路径
`recommend_path(draft, understanding)`：
- Ozon 源 → 标"试复制"(可否由 import-by-sku 探测)。
- 图=干净产品图(角色多为整体/单品) → 默认"俄化"。
- 图=营销拼图(文字密+横幅,角色杂) 或 源卡禁复制 或 WB/1688拼图 → 默认"重做"。
- 输出：推荐路径 + 各模式可用性 + 逐图默认处理（前端展示，用户可改）。

### 3.9 缓存/幂等/错误
- understanding 缓存 source_raw（重做文案/图不重读图）。
- OSS `upload_bytes` MD5 key 去重；复制 `unmatched_sku_list` 判定幂等。
- 单项 AI 失败不阻断（标待确认/占位）；出图 QC 失败重试≤2；导入轮询超时留 task_id。

---

## 4. 规模与可靠性
- **成本/SKU**：复制=0 AI；原创=多模态 1(缓存) + 文本 1~2 + gpt-image(按勾选,主图+场景+卖点,~几张到10) + 前端视频 0(浏览器)。**vision 仅理解 1 次。**
- **异步**：出图/理解挂 media_status，前端轮询；出图并发限 2~3。
- **配额**：`/v4/product/info/limit` 查每日建卡额度先拦。
- **服务器**：MySQL(Docker);字体/模型走镜像避国内下载坑;视频在前端不占服务器。

---

## 5. 取舍（显式）
| 决策 | 选 | 代价 |
|---|---|---|
| 理解：OCR vs **多模态** | **多模态** | vision 1 次(贵)；但语义准、解决数字汤、三步合一。**只一次缓存,值** |
| 文字图：PIL vs **gpt-image 渲染** | **gpt-image** | 好看融合；数字会错→**必 QC** |
| 复制：自动复制 vs 建草稿再选 | **可复制即复制不建草稿** | 最快；要改去 Ozon(用户接受) |
| 图片：整品模式 vs **逐图可控** | **逐图(俄化/重做/保留+候选)** | 控制细、省token；UI 复杂些(复用候选区) |
| 视频：后端 vs **前端幻灯片** | **前端(MP4,ffmpeg.wasm)** | 服务器零压力;后端 AI 视频另留 |
| 富文本：Ozon CDN vs **OSS 直链** | **OSS 直链**(已核实) | 简单;注意无签名/抓取前别删源 |

---

## 6. 随规模演进重审
- 多模态数字错率高 → 关键图回退"AI 留白底图+前端排版"或加 OCR 数字锚/自动复检。
- 出图成本大 → 缓存常用底图/批量降质出草图。
- 多来源 → 只加采集适配器。
- 富文本要机读分块 → 从 billboard 升结构化 widget。

---

## 现状 & 落地顺序
- ✅ 已建+实跑：`copy_flow`(import-by-sku)、`gen_image`(edit)、`listing_build`(billboard+随机货号)、`app_service`(try_copy/make_rich_content/ai_generate_image 引擎路由)、端点、前端按钮。
- ♻️ 本设计**弃用 PIL 文字路径**(`image_compose` compose_infographic/add_watermark、`make_infographic`)→ 由 gpt-image 渲染文字取代。
- 🆕 待建（落地顺序）：
  1. **`ai_multimodal` 模型槽**(settings_migrate + Settings.vue)— 地基,先做
  2. **理解层** `understand`(多模态→understanding,缓存)
  3. **`recommend_path`**(智能推荐)
  4. **图片步**：图片计划+候选区+逐图(俄化 `localize-image`/重做 `generate-image`/保留)
  5. **文案** 并入 understanding（复用 generate_card）
  6. **采集即复制**(Ozon 源 try-copy 前置)
  7. **前端**：6 步向导(照 mockup)+ ffmpeg.wasm 视频
