# 插件 1688 采集 · 设计文档

- 日期：2026-06-20
- 范围：`ozon-seller-helper-ext` 浏览器扩展，新增 1688 商品详情页采集
- 状态：已实测确认数据源，方案已通过用户评审

## 1. 背景与目标

扩展已实现 **Ozon / WB** 两条采集链路（页面就地解析 → 推后端建草稿 → 媒体异步传 OSS → 开 webui 编辑器 / 自动发布）。1688（及拼多多）目前仅有脚手架，面板停在占位 `unsupportedBody()`，按钮 disabled，无真实采集。

目标：让用户在 1688 商品详情页（`detail.1688.com/offer/*.html`）点"采集到管理端草稿"，**全量**抓取商品数据（含所有 SKU 变体），建成 Ozon 草稿，复用现有发布管线。

非目标：拼多多采集；webui 侧的翻译/AI 卡片/发布逻辑改动（沿用现有）。

## 2. 现状关键事实（已读代码确认）

- 内容脚本已注入 `https://*.1688.com/*`（`manifest.json`），站点识别 `OzonHelperSite.detectSite` → `'1688'`，币种 `currencyOf('1688')==='CNY'`。
- `collect-flow.js` 已有 `_pageCurrency()==='CNY'` 分支（国内站不换汇，直接发后端）。
- **不能复用** `_collectOne()`：它内部写死 Ozon 的 `page-json` API。须像 WB 那样单独走解析器。
- `buildCollectData(parsed)`（`product-parse.js`）是统一草稿结构，含 `rich_content_json` 字段，1688 解析器复用它。
- 媒体管线 `OzonHelperMedia.collectMediaUrls/applyMediaMap`（`media-upload.js`）已覆盖 `images[] / detail_images[] / video_url / rich_content_json` 内嵌图（`img.src`/`img.srcMobile`）。
- 后端发布：`source_raw.rich_content_json` 存在时，`to_ozon_import_item`（`drafts.py`）追加属性 **id=11254（RICH_CONTENT_ATTR_ID）**，值为紧凑 JSON 字符串。
- 推送后 `bgCall('collectParsed')` 秒回 + `bgCall('rehostPending')` 触发 background 异步把非 OSS 图/视频传 OSS（计划三）。

## 3. 1688 数据地图（浏览器实测，样本 offer 795554901999）

主数据锚点：`window.context.result.data`（模块化，真值在各模块 `.fields`）；总数据：`…data.Root.fields.dataJson`；详情：`window.offer_details.content`（HTML 字符串，**页面初始即有**）。

| Ozon 草稿字段 | 1688 来源 | 形态 |
|---|---|---|
| `title` | `data.productTitle.fields.title` | string |
| `images[]` | `data.gallery.fields.offerImgList`（40 张） | string[]（cbu/alicdn） |
| `video_url` | `data.gallery.fields.video.videoUrl` | mp4 直链（cloud.video.taobao.com）；另有 `coverUrl`/`title` |
| `rich_content_json` | `window.offer_details.content` 解析出 23 张 `<img>` → 构造富文本 | 见 §5 |
| `price` | 主品取最低 SKU 价；区间见 `data.mainPrice.fields.priceModel.originalPriceDisplay`（"18.79-141.63"） | string |
| `variants[]` | `dataJson.skuModel.skuProps`（维度轴）+ `skuModel.skuInfoMap`（35 个组合） | 见 §4 |
| `weight_g/length_mm/width_mm/height_mm` | `data.productPackInfo.fields.pieceWeightScale.pieceWeightScaleInfo[]` 按 `skuId` 匹配 | 每 SKU `{weight(克), length/width/height(mm), volume, skuId}` |
| `attributes[]` | DOM `[class*="attribute"]` 名值对（实测 55 行：产地=江苏、是否进口=否、金属材质=白铁皮…） | 名值对 |
| `description` | 留空（webui AI 生成俄语） | — |
| `category_path` | `dataJson.offerBaseInfo`（实现期确认字段，缺则留空） | string |

**SKU 模型结构（`dataJson.skuModel`）：**
- `skuProps`: `[{ fid, prop:"规格", value:[{ name, imageUrl }] }]`（此样本 1 维，多维需拼接，见 §4）
- `skuInfoMap`: `{ "<specAttrs>": { specId, specAttrs, price, discountPrice, canBookCount(库存), skuId, isPromotionSku } }`（35 个）
- 另有 `skuInfoMapOriginal` / `skuPriceScale*`（原始价/阶梯价，MVP 不用）

## 4. 全量 SKU 采集逻辑

每个 SKU 建一个草稿，全部归入同一 `variant_group`（= offerId，从 URL `offer/<id>.html` 提取）。

对 `skuInfoMap` 的每个条目：
- `price` = 该 SKU 的 `price`（CNY，不换汇）
- 库存/skuId 记录到 `source_raw`（沿用现有 source_raw 习惯，供 webui 参考）
- 变体规格名 = `specAttrs`；变体图 = 在 `skuProps[].value` 中按维度值名匹配的 `imageUrl`
  - 单维度：`specAttrs` 直接等于 `skuProps[0].value[].name`
  - 多维度：`specAttrs` 由各维度值用分隔符连接，需按维度拆分后分别匹配（实现期用一个多维商品验证拆分符）
- 克重尺寸：用 `skuId` 在 `pieceWeightScaleInfo[]` 中匹配（最可靠键），取 `weight/length/width/height`
- `images[]` = 主图 `offerImgList` + 该变体图（去重）
- `rich_content_json` / `video_url` = 全商品共用（详情图、视频对所有变体相同）

无 SKU 维度（`skuProps` 空）的商品：建单个草稿，价格取 `priceModel`。

推送：遍历串行 `bgCall('collectParsed', {url, data})`（推自己后端，无封号风险，不需 Ozon 那种 spacingMs 限速）；全部推完后 `bgCall('rehostPending')` 触发媒体异步传 OSS。进度通过 `onStatus`/`onProgress` 回面板。

## 5. 富文本（详情图）方案

1. 解析 `window.offer_details.content`（HTML）提取 `<img src>` 列表（实测 23 张，cbu01.alicdn.com）。
2. 用图列表构造 Ozon `richAnnotationJson`，图片块结构需含 `img.src`（+ `srcMobile`），以便被现有 `_collectRich` 收集。形如：
   ```json
   { "content": [ { "widgetName": "raShowcase", "type": "roll",
       "blocks": [ { "img": { "src": "<url>", "srcMobile": "<url>", "alt": "" } } ] } ] }
   ```
   **精确模板（widgetName/type/version 等）在实现期抓一个真实 Ozon A+ 商品的 `richAnnotationJson` 核对后定稿。**
3. 放入 `buildCollectData` 的 `rich_content_json`。后续：`_collectRich` 收 cbu/alicdn 图 → background 传 OSS → `_applyRich` 换 OSS 链 → 发布作为属性 id=11254。

## 6. 文件改动

1. **`common/parse-1688.js`（新）**：UMD（content script 全局 `OzonHelperParse1688` + vitest import）。
   - `parse1688Product()`：读 `window.context.result.data` / `dataJson` / `window.offer_details.content` + DOM 属性，产出传给 `buildCollectData` 的 parsed 对象（含 `rich_content_json`）。
   - `extractOfferId(url)`、`buildRichFromDetailHtml(html)`、`parseAttributesFromDom(doc)`、`matchSkuPack(skuId, packInfo)` 等纯函数，便于单测。
2. **`common/collect-flow.js`**：新增 `collect1688AndEdit(currentUrl, onStatus)`（仿 `collectWbAndEdit`，全量 SKU；CNY 不换汇）。导出加入 `OzonHelperCollect`。
3. **`content/panel.js`**：`onEditCurrent()` 与 `update()` 中 `site==='1688'` 路由到真实采集（替换占位）；展示采集/进度状态。
4. **`manifest.json`**：`content_scripts.js` 数组加入 `common/parse-1688.js`（在 `collect-flow.js` 之前）。

## 7. 测试策略

- `tests/parse-1688.test.js`（vitest，仿 `product-parse.test.js`/`wb.test.js`）：用**脱敏的最小 mock fixture**（代表性的 `context.result.data` 子集 + 一段 `offer_details.content` HTML）覆盖：
  - 标题/价格/主图/视频解析
  - 全量 SKU 展开（数量、价格、库存、skuId、变体图匹配）
  - 克重尺寸按 skuId 匹配
  - 详情 HTML → 富文本结构（图片节点可被 `collectMediaUrls` 收集）
  - 属性表名值对解析
  - 单 SKU / 无维度商品的兜底
- 不把真实 `window.context` 整体入库（含 cookie/敏感）。

## 8. 已知风险 / 实现期需定稿

- **richAnnotationJson 精确格式**：实现期抓真实 Ozon A+ 样本核对（§5）。
- **多维度 SKU 拆分符**：本样本仅 1 维，实现期用一个多维（颜色×尺寸）商品验证 `specAttrs` 的连接分隔符。
- **页面改版/字段缺失**：所有取值加防御性兜底（路径不存在不抛错，降级为空字段），关键缺失（如全局 `context` 取不到）时面板提示"请等详情加载完再采集 / 当前不是 1688 商品页"。
- **属性表 class 混淆**：用 `[class*="attribute"]` 模糊匹配，名值对解析需对 DOM 结构鲁棒（dt/dd 或 div 对）。
- **视频/详情图传 OSS 体积**：视频较大，沿用现有 background 异步管线（best-effort，失败保留原链不阻断采集）。
