---
description: 跨境一件代发盈亏测算（4 平台 · 2026-05 行情 · 含 5 项现实校准）
argument-hint: [类目=X] 成本=Y 重量=Z [售价=A] [平台=B] [广告=C] ...
---

# /pricing — 盈亏测算

调用 [.claude/skills/pricing/calc.py](../skills/pricing/calc.py) 算保本售价 / 推荐售价 / 实际盈亏。
详细公式见 [.claude/skills/pricing/SKILL.md](../skills/pricing/SKILL.md) 与 [docs/03-操作手册-QA.md §12](../../docs/03-操作手册-QA.md)。

---

## 用户输入

```
$ARGUMENTS
```

---

## 你的任务（严格执行）

### 第 1 步：解析参数

把用户输入按"键=值"切分（中英文 `=` 都接受，空格/中文逗号分隔），映射成 CLI flag：

| 中文键 | CLI flag |
|---|---|
| 成本 / cost | `--cost` |
| 重量 / weight | `--weight` |
| 类目 / category | `--category` |
| 平台 / platform | `--platform` |
| 售价 / price | `--price` |
| 佣金 / commission | `--commission` |
| 退货率 / return_rate | `--return-rate` |
| 退货处理 / return_handling | `--return-handling` |
| 收款费 / payment_fee | `--payment-fee` |
| 运费 / ship | `--ship` |
| 广告 / ad / ad_pct | `--ad-pct` |
| 工厂吞损 / factory_loss | `--factory-loss` |
| 仓贴错 / warehouse_error | `--warehouse-error` |
| 恶意退 / malicious_return | `--malicious-return` |
| 汇率buffer / fx_buffer | `--fx-buffer` |

**平台名映射**（用户可能写中文别名）：

| 用户输入 | CLI 值 |
|---|---|
| `ozon` / `Ozon` / `俄罗斯` / `俄` | `ozon` |
| `ali` / `aliexpress` / `速卖通` | `ali` |
| `temu` / `temu_y2` / `Temu Y2` / `Temu` | `temu_y2` |
| `tt` / `tiktok` / `TT` / `东南亚` / `TikTok` | `tt_sea` |

**类目原样传**（中文：家居装饰 / 收纳整理 / 宠物配件 / 办公文具 / 节日礼品 / 定制类 / 美妆 / 服装 / 通用）。

**百分比解析**：用户可能写 `广告=8%` 或 `广告=0.08`，都要转成小数（0.08）传给 CLI。同样 `退货率=5%` → `0.05`。

### 第 2 步：检查必填

- `成本` 和 `重量` 是必填
- 如果缺任何一个，**不要瞎调脚本**——回复用户索要：

  > 需要至少 2 个参数：
  > - `成本=X`（1688 采购成本，单位 ¥）
  > - `重量=X`（计费重，单位 g；= max(实重, 体积重)）
  >
  > 例：`/pricing 类目=家居装饰 成本=8 重量=100`

### 第 3 步：执行

调用：

```bash
python .claude/skills/pricing/calc.py [所有解析出的 flag]
```

例如用户输入 `类目=家居装饰 成本=8 重量=100 售价=35` →

```bash
python .claude/skills/pricing/calc.py --category 家居装饰 --cost 8 --weight 100 --price 35
```

### 第 4 步：呈现

把 calc.py 的完整输出**原样**贴给用户（已经包含格式化的表格、emoji 状态、诊断）。

如果用户没指定 `类目` 或 `平台`，在输出**之前**加一句：

> 💡 没指定 `{缺的字段}`，已用默认 `{该字段默认值}` 计算。带上能算得更准。

如果输出里显示"❌ 亏损"，**额外给一句操作建议**（≤ 1 句）：例如"建议把 1688 议到 ¥X 以下，或者换 < 100g 的同类替代品"。

### 第 5 步：（仅当用户问得开放）后续追问

如果用户没给 `售价` 但问"卖多少能赚"，主动建议 2 档：
- 保本 + 15% 缓冲（紧绷）
- 推荐售价（30% 毛利）

如果用户给了 `售价` 但状态是 `❌` 或 `⚠️`，主动提"要不要试 ¥{保本价 × 1.1}"。

---

## 无参数时

如果 `$ARGUMENTS` 为空，回复以下帮助：

```
🧮 /pricing 跨境一件代发盈亏测算

必填：
  成本=¥ 重量=g

可选：
  类目=家居装饰|收纳整理|宠物配件|办公文具|节日礼品|定制类|美妆|服装|通用
  平台=ozon|ali|temu_y2|tt_sea（默认 ozon）
  售价=¥（检查当前定价能不能赚）
  广告=8%、工厂吞损=5%、退货率=10% 等任一覆盖

例子：
  /pricing 类目=家居装饰 成本=8 重量=100
  /pricing 成本=6 重量=80 类目=宠物配件 售价=30
  /pricing 成本=12 重量=150 平台=tt 类目=收纳整理 广告=10%
```
