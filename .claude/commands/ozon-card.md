---
description: 给一个商品链接，生成符合 Ozon 2026 规则的卡片草稿（俄语标题/描述 + 属性表 + 图片清单 + 合规自查）
argument-hint: <商品链接> [类目=X] [重量=Yg] [颜色=A/B] [品牌=Z]
---

# /ozon-card — Ozon 商品卡片生成

按 [ozon/card-requirements.md](../../ozon/card-requirements.md) 的规则，把一个商品链接转成可粘进 Ozon 后台的卡片草稿。
详细步骤见 [.claude/skills/ozon-card/SKILL.md](../skills/ozon-card/SKILL.md)。

---

## 用户输入

```
$ARGUMENTS
```

---

## 你的任务

### 第 1 步：解析参数

第一个非 `键=值` 形式的 token 是**商品链接**（必填）。其余按键值对解析：

| 键 | 用途 |
|---|---|
| 类目 / category | 覆盖类目自动推断 |
| 重量 / weight | 如果链接抓不到 |
| 颜色 / color | 多色用 `/` 分隔 |
| 品牌 / brand | 默认 `Нет бренда` |
| 尺寸 / size | 长×宽×高 cm |

### 第 2 步：检查必填

如果没有链接，回复：

> 需要商品链接：
> - `/ozon-card https://detail.1688.com/offer/xxx.html`
> - `/ozon-card https://item.taobao.com/item.htm?id=xxx`
> - 可选追加：`类目=家居装饰 重量=120g 颜色=白/黑`

### 第 3 步：执行 skill

按 [.claude/skills/ozon-card/SKILL.md](../skills/ozon-card/SKILL.md) 8 步流程执行：
1. 读 ozon/card-requirements.md 拿规则
2. WebFetch 商品链接抓信息
3. 推断类目（用户没指定时）
4. 生成俄语标题（过禁用词、控长度）
5. 生成俄语描述（5 项必含）
6. 生成属性表
7. 生成图片清单（每张写处理要求）
8. 合规自查 checklist

### 第 4 步：呈现

按 SKILL.md 的"输出格式"小节给一份完整 markdown，结构：
1. 标题（俄）
2. 描述（俄）
3. 属性表
4. 图片清单
5. 合规自查
6. 下一步行动

抓不到的字段标 `[待补]`，**不许编**。

---

## 无参数时

如果 `$ARGUMENTS` 为空，回复：

```
🇷🇺 /ozon-card — Ozon 卡片生成

必填：
  <商品链接>（1688 / 淘宝 / 阿里巴巴国际站）

可选：
  类目=家居装饰|收纳整理|宠物配件|办公文具|节日礼品|定制类|通用
  重量=Xg（链接抓不到时手动给）
  颜色=A/B/C（多色用斜杠）
  品牌=...（默认 Нет бренда）
  尺寸=10×8×5 cm

例子：
  /ozon-card https://detail.1688.com/offer/123.html
  /ozon-card https://detail.1688.com/offer/123.html 类目=收纳整理 重量=200g
  /ozon-card https://item.taobao.com/item.htm?id=xxx 颜色=白/黑/灰

输出：俄语标题 + 俄语描述 + 属性表 + 图片处理清单 + 合规自查
规则源：ozon/card-requirements.md（2026-05-12 确认）
```
