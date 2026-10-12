---
name: scout
description: 跨境选品可行性分析(Ozon 版)。给一个产品关键词，自动搜 1688 进价 + Ozon 竞品价，调用 ozon-profit-calculator 算各物流渠道(ZTO/OGL/China Post)的保本价、推荐售价与利润，输出"能不能做"的结论。触发：/scout、"这个品能做吗""帮我看看XX能不能卖""选品分析""竞品调研"等。
---

# 跨境选品可行性分析 Skill（Ozon 版）

## 用途

输入一个产品关键词（中文或英文），自动完成：
1. **搜 1688 进价** — 找到供货价区间和重量
2. **搜 Ozon 竞品价** — Ozon 上同类产品的在售价格分布
3. **调用 ozon-profit-calculator** — 用进价+重量算 ZTO / OGL / China Post 各渠道的保本价、推荐售价、单件利润
4. **对比出结论** — Ozon 竞品价 vs 我们成本，判断能不能做 + 推荐最优物流渠道

> 定价依赖 `ozon-profit-calculator`（`E:\personal\ozon-helper\.agents\skills\ozon-profit-calculator\scripts\calc_profit.py`）。

## 调用格式

```
/scout 宠物牌 定制刻字 不锈钢
/scout 可降解宠物拾便袋
/scout 胎压监测器
```

带已知参数缩短搜索：
```
/scout 宠物除毛手套 进价=8 重量=30
/scout 汽车诊断仪 进价=480 重量=450 类目=汽车用品
```

## 执行步骤

### Step 1: 搜 1688 进价

用 WebSearch 搜索：`1688 {产品关键词} 一件代发` 或 `site:1688.com {关键词}`

提取：
- **进价区间**（最低价 / 主流价 / 品质款价）
- **重量估算**（从商品描述或常识推断）
- **起订量**（是否支持一件代发）
- **产地**（义乌/深圳/东莞等）

如果用户已给 `进价=X 重量=Y`，跳过此步。

### Step 2: 搜 Ozon 竞品价

**优先用本仓自带 scraper**，比 WebSearch 精准：
```bash
$env:PYTHONPATH = "tools/ozon-scraper"
python -m ozon_scraper scout "{俄语关键词}" --limit 30
```
输出 JSON 含：
- `price.min / p25 / median / p75 / max` —— 价格分布（RUB）
- `discount_pct.median` —— 普遍折扣率
- `review_count.median / max / gte_1000` —— 市场体量信号
- `top_3_by_reviews` —— 头部 3 个 SKU

主流价取 `price.p25 ~ price.p75`；`review_count.gte_1000` 占比高说明红海类目。scraper 失败或过冷门（结果<5）时回退 WebSearch `ozon {俄语关键词} цена`。

### Step 3: 调用 ozon-profit-calculator

用 Step 1 的进价和重量调用：

```bash
# 反推目标售价(默认 10% 毛利)
python E:\personal\ozon-helper\.agents\skills\ozon-profit-calculator\scripts\calc_profit.py --cost {进价} --weight {重量} --target-margin 0.10 [--category car|other]

# 用 Ozon 竞品价看实际利润
python E:\personal\ozon-helper\.agents\skills\ozon-profit-calculator\scripts\calc_profit.py --price {竞品主流价} --cost {进价} --weight {重量} [--category car|other]
```

从输出拿（每渠道 ZTO/OGL/ChinaPost陆运/ChinaPost空运）：
- `推荐物流` + 建议售价
- 各渠道 `利润` / `利润率` / `物流费`
- 竞品价下各渠道利润 → 判断空间

类目判断：**汽车用品/汽配/车载/诊断/胎压 → `--category car`（RFBS 12%/17% 档）；其他 → `--category other` 并提示给佣金率**。

### Step 4: 对比 & 出结论

比较：
- **Ozon 竞品主流价 vs 我们推荐售价** → 能不能做
- **各渠道利润** → 走哪个物流最赚
- **退货抗性** → 利润薄时提示退1单补几单

## 输出格式（markdown 表格）

### 产品信息

> **{产品名}** · 1688 进价 ¥{X}-{Y}（取 ¥{Z}） · 约{W}g · 类目：{类目}

### Ozon 竞品价 vs 我们的成本（各物流渠道）

| 渠道 | 推荐售价(10%毛利) | 竞品主流价 | 竞品价下利润 | 判定 |
|---|---|---|---|---|
| ZTO | ¥Z | ₽X | ¥N | ✅/⚠️/❌ |
| OGL | ¥Z | ₽X | ¥N | ✅/⚠️/❌ |
| China Post 陆运 | ¥Z | ₽X | ¥N | ✅/⚠️/❌ |
| China Post 空运 | ¥Z | ₽X | ¥N | ✅/⚠️/❌ |

### 判定规则

- **✅ 能做**：推荐售价 ≤ 竞品主流价，且有利润空间
- **⚠️ 勉强**：推荐价贴近竞品价上端，或利润薄（<10%）
- **❌ 做不了**：保本价 ≥ 竞品价，数学上不可能盈利

### 结论

- **推荐物流**：利润最高的渠道 + 理由
- **能否做**：主结论（✅/⚠️/❌）+ 关键数字
- **风险提示**：定制品？红海？合规？季节性？退货率？
- **下一步**：1688 搜索词 + 建议操作

## 类目自动判断（佣金档映射）

- 汽车/汽配/车载/诊断/胎压/传感器/示波器 → `car`（汽车用品 RFBS，≤1500R=12%、>1500R=17%）
- 其他 → `other`（需用户给定佣金率，或用默认值并标注）

## 注意事项

- 竞品价格搜索结果可能不完整，标注数据来源和搜索时间
- Ozon 用俄语搜效果更好
- 对比时统一换算为 CNY；汇率/费率以 `calc_profit.py` 当天参数为准
- China Post 两渠道限重 ≤500g、货值 ≤1500 卢布，超限会被自动标为不可用，别误判为无此渠道
