---
name: ozon-stats
description: Ozon 店铺流量/转化数据速查。拉取曝光/会话/加购/转化/下单/退货/取消/金额，默认昨天，支持日期区间；输出全店汇总 + 分 SKU（带俄语商品名）+ 按天趋势 + 自动解读。触发：/ozon-stats、"看下昨天的曝光/点击/加购""Ozon 数据""店铺流量怎么样""昨天卖了多少"等。
---

# Ozon 流量/转化数据速查 Skill

## 用途

一条命令拉 Ozon 卖家后台的流量漏斗数据（走 `/v1/analytics/data`），帮卖家快速看：
- 全店昨天/某区间的曝光、会话、加购、下单、金额
- 每个 SKU 的表现（带俄语商品名，自动反查）
- 区间趋势（按天）
- 自动解读：爆款识别、漏斗转化、客单价、零曝光长尾

## 数据来源

- 抓数脚本：`.claude/skills/ozon-stats/fetch.py`（纯标准库，无依赖）
- API key：自动从 `tools/ozon-listing-webui/data/products.db` 的 `settings` 表读
- 接口：`/v1/analytics/data`（限 **1 分钟 1 次**，脚本一次性拿全维度）+ `/v3/product/info/list`（反查标题）

## 执行步骤

### Step 1: 算日期范围 → 跑脚本

| 用户意图 | 命令 |
|---|---|
| 昨天（默认） | `python .claude/skills/ozon-stats/fetch.py` |
| 单日 | `python .claude/skills/ozon-stats/fetch.py --date 2026-06-05` |
| 区间 | `python .claude/skills/ozon-stats/fetch.py --from 2026-06-01 --to 2026-06-05` |
| 滚动 N 天 | `python .claude/skills/ozon-stats/fetch.py --days 7` |

脚本把结果写到 `.claude/skills/ozon-stats/_last.json` 并 print 一行状态（`OK ...` / `OK_EMPTY ...`）。
**不要直接看脚本的 stdout 取数**（Windows 控制台会把俄语/中文打成乱码）——下一步用 Read 读 JSON。

### Step 2: Read `_last.json`

用 Read 工具读 `.claude/skills/ozon-stats/_last.json`。结构：
- `meta`：date_from/date_to、row_count、truncated（是否超 1000 行被截断）、api_timestamp
- `totals`：全店汇总
- `by_sku`：分 SKU（已按曝光降序），含 `name`（俄语标题，可能为空）
- `by_day`：按天聚合（区间 >1 天时用来画趋势）

指标字段：`hits_view`曝光 / `session_view`会话 / `hits_tocart`加购 / `conv_tocart`加购转化率% / `ordered_units`下单 / `returns`退货 / `cancellations`取消 / `revenue`金额₽。

### Step 3: 按下面格式输出

## 输出格式（markdown，中文）

### 全店汇总

> **{date_from} ~ {date_to}** · 取数时间 {api_timestamp}

| 曝光 | 会话 | 加购 | 转化% | 下单 | 退货 | 取消 | 金额₽ |
|---:|---:|---:|---:|---:|---:|---:|---:|
| … | … | … | … | … | … | … | … |

### 分 SKU（按曝光降序）

| 排名 | SKU | 商品名 | 曝光 | 会话 | 加购 | 下单 | 退货 | 金额₽ |
|---|---|---|---:|---:|---:|---:|---:|---:|

- `name` 为俄语标题，给出俄语 + 一句中文意译；name 为空时标 `[未反查到]`。
- SKU 较多（>15）时只列前 15 + 一行"其余 N 个 SKU 合计"，避免刷屏。

### 按天趋势（仅当区间 > 1 天）

| 日期 | 曝光 | 会话 | 加购 | 下单 | 金额₽ |
|---|---:|---:|---:|---:|---:|

### 自动解读

按数据给 2-4 条洞察，例如：
- **爆款识别**：流量/成交是否集中在个别 SKU（算占比）
- **漏斗**：曝光→会话→加购→下单 各环节转化，指出卡在哪一环
- **客单价**：revenue / ordered_units
- **零曝光长尾**：曝光个位数、零转化的 SKU 先别投入
- **退货/取消**异常（若 >0）

### 下一步建议

1-3 条可执行建议（放大哪个 SKU、优化哪一环、哪些先观察）。

## 错误处理（脚本已处理，照实转述）

- stdout 是 `OK_EMPTY` → 该时段无流量，告诉用户"这段时间没有数据"
- 脚本报 `ERROR: ... 403` → 账号可能没订阅 Premium，曝光/加购类指标不可用
- 脚本报 `ERROR: ... 找不到 products.db / 没有 ozon_client_id` → 让用户去 ozon-listing-webui WebUI 设置页配 Client-Id / Api-Key
- `meta.truncated == true` → 提示区间过大被截断到 1000 行，建议缩小区间

## 注意

- `/v1/analytics/data` 限 1 分钟 1 次。连续两次调用之间若报 429，脚本会自动等 60 秒重试一次。
- `conv_tocart` 在聚合层用 加购/会话 重算，和单看某行 API 原值可能略有出入，这是正常的。
- 金额单位是卢布 ₽。
