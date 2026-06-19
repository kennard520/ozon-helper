---
description: 拉取 Ozon 店铺流量/转化数据（曝光/会话/加购/下单/金额），默认昨天，支持日期区间；输出全店汇总 + 分 SKU（带俄语名）+ 趋势 + 解读
argument-hint: [日期/区间，如 2026-06-05 或 2026-06-01~2026-06-05 或 近7天，省略=昨天]
---

# /ozon-stats — Ozon 流量/转化数据速查

拉 Ozon 卖家后台流量漏斗数据。详细步骤见 [.claude/skills/ozon-stats/SKILL.md](../skills/ozon-stats/SKILL.md)。

---

## 用户输入

```
$ARGUMENTS
```

---

## 你的任务

### 第 1 步：解析时间范围 → 拼脚本参数

把自然语言翻成 `fetch.py` 的 flag：

| 用户输入 | 脚本命令 |
|---|---|
| （空） | `python .claude/skills/ozon-stats/fetch.py` |
| `2026-06-05` | `... --date 2026-06-05` |
| `2026-06-01~2026-06-05` 或 `2026-06-01 到 2026-06-05` | `... --from 2026-06-01 --to 2026-06-05` |
| `近7天` / `7天` / `7d` | `... --days 7` |
| `近30天` / `30d` | `... --days 30` |

- 区间分隔符 `~`、`-`、`到`、`至` 都按区间处理。
- 今天是 currentDate；"昨天"=today-1，脚本无参时自动取昨天，不用自己算。

### 第 2 步：跑脚本

执行拼好的命令。脚本把数据写到 `.claude/skills/ozon-stats/_last.json`，stdout 给一行状态。
**不要**从 stdout 读数据（中文/俄语会乱码）。

### 第 3 步：Read `_last.json` → 按 SKILL.md 输出格式呈现

读 `.claude/skills/ozon-stats/_last.json`，按 [SKILL.md](../skills/ozon-stats/SKILL.md) 的"输出格式"出：
全店汇总 → 分 SKU（带俄语商品名 + 中文意译）→ 按天趋势（区间>1天才出）→ 自动解读 → 下一步建议。

---

## 无参数时

直接按"昨天"跑（不用追问）。如果脚本报缺 key，再提示用户：

```
📊 /ozon-stats — Ozon 流量/转化数据

用法：
  /ozon-stats                       # 昨天
  /ozon-stats 2026-06-05            # 某一天
  /ozon-stats 2026-06-01~2026-06-05 # 区间
  /ozon-stats 近7天                  # 滚动 7 天

指标：曝光 / 会话 / 加购 / 转化率 / 下单 / 退货 / 取消 / 金额₽
输出：全店汇总 + 分 SKU（带俄语商品名）+ 按天趋势 + 自动解读

需先在 ozon-listing-webui WebUI 设置页配好 Ozon Client-Id / Api-Key。
数据走 /v1/analytics/data，限 1 分钟 1 次。
```
