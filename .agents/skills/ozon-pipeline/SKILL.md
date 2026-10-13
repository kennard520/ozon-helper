---
name: ozon-pipeline
description: Ozon 选品→上架全流程一条龙（本地单文件）。链路：Ozon 自动逛搜索页收集 SKU → BCS 查月销/月GMV/跟卖/转化/佣金表 → 1688 国际站查进价 → 调 ozon-profit-calculator 算各渠道利润 → 按月销/利润筛选 → 下载素材（标记待处理） → [agent 接力] 豆包 AI 原创生成处理素材 → 生成上架载荷。触发：/ozon-pipeline、"自动选品""帮我逛 Ozon 找能卖的品""选一批品分析利润""自动上架选品"等。
---

# Ozon 选品→上架全流程（ozon-pipeline）

把从"逛 Ozon"到"上架准备"的整条链路串成一个本地单文件脚本，不依赖任何 worker。

## 链路

```
① Ozon 自动逛  cloakbrowser 登录态浏览器翻搜索页，收集 SKU
② BCS 查数    调 ozon.bcserp.com/prod-api/system/sku/skuss/new
              → 月销 monthsales / 月GMV monthgmv / 均价 avgprice / 转化 convToCartPdp
                / 点击率 goodsClickRate / 佣金表 commission / 图片 skuimg
③ 国内进价    1688 国际站(alibaba.com)搜同款 → US$ 区间（失败不阻塞）
④ 算利润      调 ozon-profit-calculator/scripts/calc_profit.py（ZTO/OGL/ChinaPost 四渠道）
⑤ 筛选        月销≥阈值 & 利润≥阈值 & 售价≤上限
⑥ 素材        下载竞品主图到 picks_output/assets/
⑦ 处理素材    [agent 接力] 豆包 AI 原创生成：image_edit 抠图去背景留产品本体 →
              image_edit / image_gen 原创白底/场景/信息图 → assets_processed/<sku>/（不直接上架）
⑧ 上架载荷    生成 listing_payload（images 引用处理图；最终上架图需 agent AI 原创生成后以 OSS 直链替换）
```

## 用法

```bash
# 完整跑（用项目 venv 的 python，因为依赖 cloakbrowser）
E:\code\zqr\ozon-helper\.venv\Scripts\python.exe `
  E:\code\zqr\ozon-helper\.agents\skills\ozon-pipeline\scripts\pipeline.py "мультиметр" --pages 2

# 多关键词、调阈值
... pipeline.py "мультиметр" "pH метр" --pages 3 --min-sales 100 --min-profit 30 --max-price 6000

# 跳过某阶段
... pipeline.py "мультиметр" --skip-price        # 不查 1688 进价
... pipeline.py "мультиметр" --skip-bcs          # 不查 BCS

# 复用上次结果续跑（不重新逛）
... pipeline.py --resume picks_output\pipeline_20261012_*.json

# 手动给 SKU 列表直接查数+算利润
... pipeline.py --skus 4789122822,148555165 --no-browser
```

## 配置

`scripts/config.json`：
- `BCS_TOKEN` / `BCS_LIMIT_KEY` — 插件登录态，从浏览器 Network 里 `Authorization: Bearer xxx` 和 `X-Limit-Key` 复制。也可用环境变量 `BCS_TOKEN`/`BCS_LIMIT_KEY` 覆盖。
- `RUB_TO_RMB` 汇率、`MIN_SALES`/`MIN_PROFIT_RMB`/`MAX_PRICE_RUB` 筛选阈值、`CATEGORY` car|other（汽车用品走 12/17% 档）。
- ⚠️ config.json 含私人 token，勿提交 git。

### BCS token 过期怎么办（自动登录取新 token）

BCS 网页登录有阿里云滑块验证（headless 拖不动），流程：

```bash
# 1. 用项目 venv 启动有头浏览器，自动填账号密码并点登录
cd E:\code\zqr\ozon-helper
& ".\.venv\Scripts\python.exe" -c "..."   # 见 AGENTS.md「BCS 凭证」章节的方法
# 2. 浏览器窗口弹出后，人工拖动滑块到最右边
# 3. 登录成功后（URL 跳到 /home/bcs），脚本自动抓取：
#    - localStorage / cookie 里的 Admin-Token、Limit-Key
#    - 或 Network 请求头 Authorization / X-Limit-Key
# 4. 把新 token 写回 scripts/config.json
```

登录后 token 存在于：
- cookie `Admin-Token`（=`Bearer` 后的 JWT）、cookie `Limit-Key`
- 任意发往 `ozon.bcserp.com/prod-api` 请求的 `Authorization: Bearer ...` + `X-Limit-Key: ...`

账号密码见 AGENTS.md「BCS（卖家国度）凭证（明文）」。

## 输出

- `picks_output/pipeline_YYYYmmdd_HHMMSS.json` — `all`(全量+BCS+利润) / `picks`(候选) / `listing_payload`(上架载荷)
- `picks_output/assets/` — 候选商品主图（竞品图，仅参考）
- `picks_output/assets_processed/<sku>/` — 豆包 AI 原创生成的处理产物（抠图 + 原创白底/场景/信息图；`image_status=processed_doubao`，上架前以 OSS 直链替换载荷 images）

## 与 scout 的分工

- `scout` = 单个关键词的可行性分析（1688进价 + Ozon价格分布 → 能不能做），**不接 BCS**。
- `ozon-pipeline` = 批量逛 + BCS 真实销售数据 + 筛选 + 素材 + 上架载荷，是你要的完整链路。
- 利润口径统一走 `ozon-profit-calculator`（佣金+四渠道物流，含 2% 代理 + 0.33% 跨境），不接税务类 skill。

## 上架规则（强制）

- **禁止使用** `/v1/product/import-by-sku`（复制上架通道）——竞品多开禁止复制，且跨境店复制会被审核拦截。
- 上架一律走 `/v3/product/import` **原创建卡**。
- **定价规则**（Ozon 后台 4 个价格字段）：
  - 建议销售价 = 竞品均价换算成人民币
  - 非促销最高价格（price）= 建议销售价 × 1.9
  - 划线价格（old_price）= 建议销售价 × 4
  - 促销活动限制价格（marketing_price）= 建议销售价
  - 成本（cost）= 建议销售价

## 已知限制

- Ozon 搜索页必须用 cloakbrowser（普通 requests 会 403 TLS 指纹拦截）；profile 复用 `picks_output/.ozon_tmp_profile` 保留反爬 cookie。
- 无 BCS 数据的商品会跳过筛选（`bcs=None`）。
- 重量未在 BCS 返回中，calc_profit 用默认 300g，建议筛出候选后手动核重（或后续接 Ozon entrypoint API 读 4497/9454/9455/9456 属性）。
- 上架第 8 步目前只生成载荷 JSON；配好 Ozon Seller API `Client-Id` + `Api-Key` 后可接 `v3/product/import`。
- **处理素材 = 豆包 AI 原创生成**（由 agent 接力执行）：`image_edit` 抠图去背景留产品本体 → `image_edit` / `image_gen` 原创白底/场景/信息图；产物标记 `image_status=processed_doubao`，不直接上架。
- 最终上架图必须由豆包 AI（`image_edit` / `image_gen`）以卖点/参数为准生成全新画面（竞品图仅参考，不以竞品画面为锚点；不保留竞品水印/文字/品牌元素），再以 OSS 公网直链替换载荷 `images` 字段。
