---
name: price
description: 跨境一件代发盈亏测算 v3（4 平台 · 实时汇率 · 平台×类目佣金 · 含现实校准）。给 1688 成本+重量，算出 4 平台保本/推荐售价、每单利润、竞品价对比。未指定类目时输出全类目×全平台矩阵。触发：/price、"定价多少""成本X卖多少""能不能做""毛利怎么算"等。
---

# 跨境一件代发盈亏测算 v3

## 用途

输入 1688 成本 + 重量，自动计算：

1. **保本售价** — 不亏的最低价
2. **推荐售价** — 留 30% 毛利
3. **每单利润绝对值** — 不只看毛利率
4. **加价倍率 & 运费占比**
5. 如给 `售价` → 实际利润/毛利/盈亏诊断
6. 如给 `竞品价` → 按竞品价能不能做

**核心特性**：
- 汇率实时获取（open.er-api.com），失败回退缓存
- 所有参数外置到 `params.json`，可手动调整
- 佣金按 **平台×类目** 二维表（不是统一值）
- 运费按 **阶梯函数**（首重/续重）
- 未指定类目 → **全类目×全平台矩阵**
- **Ozon 平台 + 竞品价** → 自动算 Price Index（曝光加权关键指标，见 [ozon/pricing-rules.md](../../../ozon/pricing-rules.md) §1）

---

## 调用约定

### 必填
- `cost`：1688 采购成本 ¥（含国内到货代仓运费，或另填 domestic_ship）
- `weight`：实际重量 g

### 强烈推荐
- `category`：类目。**不填=全类目矩阵输出**（因各类目佣金不同）
- `platform`：ali / temu_y2 / tt_sea / ozon / all（默认 all）

### 可选
- `price`：当前售价 ¥ → 算实际利润
- `market_price`：竞品售价 ¥ → 判断能不能竞争
- `length` / `width` / `height`：包装尺寸 cm → 自动算体积重
- 费率覆盖：`commission` / `return_rate` / `return_handling` / `payment_fee` / `ship` / `promo_discount`
- 额外成本：`domestic_ship`(国内运费) / `packing_fee`(包装费,默认¥3) / `import_tax`(进口税)
- 现实校准：`ad_pct` / `factory_loss` / `warehouse_error` / `malicious_return` / `fx_buffer` / `affiliate_pct`(达人佣金) / `seasonal_surcharge`(旺季附加)

### 调用示例
```
/price 15 200                                  ← 全类目×全平台矩阵
/price 15 200 家居装饰                          ← 4平台 单类目
/price 20 500 ozon 宠物配件                     ← 单平台 单类目
/price 20 300 售价=80                           ← 检查售价是否盈利
/price 10 100 竞品价=40                         ← 竞品价能不能做
/price 10 100 长=15 宽=10 高=8                  ← 自动算体积重
/price 8 100 广告=0.08 达人=0.1                 ← 起量后投广告+达人
/price 25 500 旺季=0.25                         ← Q4 旺季附加 25%
```

---

## 执行步骤

1. 解析用户参数（中文关键词映射到 CLI 参数）
2. 调用：`python .claude/skills/price/calc.py --cost X --weight Y [--category ...] [--platform all] --output json`
   - **必须用 `--output json`** 拿结构化数据
   - 未指定类目时不传 `--category`（脚本自动跑全类目）
   - 汇率自动实时获取（离线自动回退缓存）
3. **用 markdown 表格渲染结果**（不要直接贴 pretty 输出）

### 参数映射（用户中文 → CLI）
- 类目/品类 → --category
- 平台 → --platform
- 售价/卖价 → --price
- 竞品价/市场价 → --market-price
- 长/宽/高 → --length/--width/--height
- 国内运费 → --domestic-ship
- 包装费 → --packing-fee
- 进口税 → --import-tax
- 活动折扣 → --promo-discount
- 广告 → --ad-pct
- 达人/达人佣金 → --affiliate-pct
- 旺季/旺季附加 → --seasonal-surcharge
- 工厂吞损 → --factory-loss
- 仓错 → --warehouse-error

---

## 公式（v3）

```
实际运费 = ship(billable_weight) × (1 + seasonal_surcharge)
固定成本 = cost + domestic_ship + packing_fee + 实际运费 + import_tax
损失率 L = return_rate + malicious_return + factory_loss + warehouse_error
有效退货处理 = (return_rate + malicious_return + warehouse_error) × return_handling
收入系数 = (1 - promo_discount) × (1 - commission - payment_fee - ad_pct - fx_buffer - affiliate_pct)

P_min = (固定成本 + 有效退货处理) / [(1 - L) × 收入系数]
P_target = P_min / (1 - 0.30)
每单利润 = (1-L) × P × 收入系数 - 固定成本 - 有效退货处理
```

---

## 输出格式（Claude 用 markdown 渲染）

### 全类目矩阵模式（未指定类目时）

从 JSON 里读取 `results[category][platform]` 矩阵，渲染为：

#### 输入确认
> 进价 ¥X，重量 Xg，汇率：实时/缓存

#### 1. 保本售价矩阵 (¥)

| 类目 | AliExpress | Temu Y2 | TikTok SEA | Ozon FBS |
|---|---|---|---|---|
| 家居装饰 | ¥X | ¥X | ¥X | ¥X |
| ... | | | | |

#### 2. 推荐售价矩阵 (¥, 30%毛利)

同上格式

#### 3. 每单利润矩阵 (¥, 推荐售价下)

同上格式

#### 4. 佣金率对照

| 类目 | AliExpress | Temu Y2 | TikTok SEA | Ozon FBS |
|---|---|---|---|---|
| 家居装饰 | 8% | 0% | 6% | 14% |
| ... | | | | |

#### 5. 推荐结论
- 最优组合（类目+平台）、最高门槛、风险提示

### 全平台单类目模式（指定了类目时）

#### 1. 隐性损耗表
#### 2. 4 平台成本拆解（含新增项：国内运费、包装费、活动折扣、达人佣金等）
#### 3. 4 平台建议售价（含保本、推荐、本币、加价倍率、运费占比、**每单利润**）
#### 4. 裸公式 vs 含校准对比
#### 5. 如有售价/竞品价：利润对比表
#### 6. 推荐结论 + 诊断

### 单平台单类目模式

竖向详细表（固定成本拆解、费率、损失率、结果、诊断）

---

## 配置文件 params.json

所有可变参数存储在 `.claude/skills/price/params.json`：
- `exchange_rates`：汇率（运行时自动刷新）
- `commission`：平台×类目 二维佣金表
- `shipping_brackets`：各平台阶梯运费
- `categories`：类目退货率/退货处理费
- `platforms`：平台收款费/活动折扣/汇率buffer等
- `reality_defaults`：现实校准默认值（广告/工厂吞损/仓错/恶意退/达人/旺季/包装/国内运费/进口税）

用户可直接编辑此文件调整参数，无需改代码。

---

## 诊断规则（calc.py 内置）

| 条件 | 提示 |
|---|---|
| 加价倍率 < 3x | 抗波动薄 |
| 运费占比 > 40% | 物流吃利润 |
| 运费占比 > 25% 且 > 300g | 注意体积重 |
| 退货率 > 10% | 类目选对了吗 |
| > 500g 且 Ozon | 考虑 FBO 备货 |
| Ozon 保本 < ¥27 | 低价保护佣金 |
| 校准抬升 > 5% | 显示裸vs校准差额 |
| 体积重 > 实重 | 提示按体积重计费 |
| 旺季附加 > 0 | 标注旺季运费 |
| Temu Y2 | 提醒供货价模式 |
| 竞品价 < 保本 | 该平台做不了 |
| 毛利 < 15% | 紧绷 |
| 毛利 >= 30% | 可上架 |
| profit < 0 | 亏损 |
| Ozon Price Index ≤ 1.02 | 🟢 +7.5% 曝光加权 |
| Ozon Price Index 1.02-1.05 | 🟡 +5% 曝光 |
| Ozon Price Index 1.06-1.29 | 🔴 无曝光加权 |
| Ozon Price Index ≥ 1.30 | 🔴🔴 强制不利 |

---

## Ozon Price Index（关键）

只在 `platform=ozon` **且**给了 `market_price` 时触发。规则源：[ozon/pricing-rules.md](../../../ozon/pricing-rules.md) §1。

输出字段（JSON 里在 `results[cat][ozon]`）：
- `price_index`：推荐价 / 竞品最低价 的比值
- `price_index_level`：`green` / `yellow` / `red` / `red_forced`
- `price_index_label`：含 emoji 中文标签
- `search_boost`：曝光加权（0.075 / 0.05 / 0）
- `price_for_green`：入绿区的最高定价（= 竞品 × 1.02）
- `price_for_yellow`：入黄区的最高定价（= 竞品 × 1.05）

**Ozon 推荐定价 SOP**（详见 ozon/pricing-rules.md §8）：

1. 不带 market_price 跑一次 → 拿到 `target_cny`（30% 毛利目标价）
2. 在 ozon.ru 搜同款找最低价 → 加 `市场价=M` 再跑一次
3. 看 Price Index：
   - 🟢 ≤ 1.02 → 直接用 target_cny
   - 🟡 1.02-1.05 → 看是否值得降到 `price_for_green` 换 +2.5% 曝光
   - 🔴 ≥ 1.06 → 必须降到 `price_for_yellow` 或 `price_for_green`，否则没曝光
4. 设最低价 = max(保本×1.05, price_for_green×0.95)
5. 决定是否开"保持优惠价格"自动跟价（标品开，非标关）
