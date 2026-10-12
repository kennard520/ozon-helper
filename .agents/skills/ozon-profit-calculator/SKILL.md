---
name: ozon-profit-calculator
description: "计算 Ozon 俄罗斯站跨境(RFBS, 中国内地发货)商品的单件利润与成本: 销售佣金 + 物流(四个渠道: ZTO 合作物流 / OGL Ozon Global Logistics / China Post to PUDO 陆运Economy / 空运Standard, 均含2%代理费与0.33%跨境代理费), 对比各物流渠道并推荐更省钱的渠道, 推荐达到目标利润率的售价。触发场景: 用户问『这款商品利润/成本/运费/佣金多少』『走 ZTO 还是 OGL 划算』『卖多少钱合适/怎么定价』『帮我算一下这个产品赚不赚钱』, 或跨境电商卖家需要核算 Ozon 商品利润、物流对比或定价时使用。默认按汽车用品(RFBS 17%档佣金)口径。"
---

# Ozon 利润计算器

算 Ozon 俄罗斯站跨境卖家单件商品的**利润 / 成本 / 物流对比 / 推荐售价**。

## Quick Start

核心脚本: `scripts/calc_profit.py`(确定性计算, 可直接运行)。

```bash
python calc_profit.py --price <售价CNY> --cost <进货CNY> --weight <重量g> [--channel all|zto|ogl|china_post|china_post_air] [--target-margin 0.10] [--rate 汇率]
```

- 缺省 `--channel` 时对比 ZTO / OGL / ChinaPost陆运 / ChinaPost空运 四渠道并推荐利润最高者。
- 缺省 `--target-margin 0.10` 时给出达到 10% 利润率的建议售价。
- `--rate` 默认 12.7154(2026-10-09 新浪收盘), 下单日按当天汇率覆盖传入。
- 批量: `python calc_profit.py --file goods.json`, JSON 为数组 `[{"name":"..","price":129,"cost":36,"weight":450}, ...]`。
- `--json` 输出结构化 JSON。

### 示例

```bash
# 单商品, 对比三渠道并给推荐售价(目标10%)
python calc_profit.py --price 452 --cost 311 --weight 750 --target-margin 0.10

# 只算 OGL
python calc_profit.py --price 452 --cost 311 --weight 750 --channel ogl

# 批量
python calc_profit.py --file goods.json --rate 12.6
```

## 输出口径

对每个商品, 脚本输出(每件, 人民币):

- **售价 / 进货 / 重量 / 货值(卢布) / 佣金率**
- **ZTO(Standard 档)** / **OGL** / **ChinaPost陆运(WH Economy)** / **ChinaPost空运(WH Standard)**: 评分组、承运/运输费、2% 代理费、0.33% 跨境代理费、物流合计、佣金、总成本、**利润、利润率**
- **推荐物流**: 四渠道中利润最高的渠道
- **推荐售价**: 达到 `--target-margin` 目标利润率的最小售价(在推荐渠道下二分求解)

## 费用构成(务必向用户讲清, 含三笔隐藏项)

1. **销售佣金** — 按货件卢布价值分档: 汽车用品 RFBS `≤1500R=12%`、`>1500R=17%`。`--category other` 时用 `--commission` 固定值。
2. **Ozon 电子服务/代理费** — 货件价值 **2%**, 每件**封顶 15~200 卢布**(三个渠道都收)。
3. **承运商配送费 / OGL 运输服务费** — ZTO 与 OGL 按评分组的 `fix + var/g`; **China Post to PUDO 陆运(WH Economy)=`1.9元/件+26元/KG`、空运(WH Standard)=`1.9元/件+67元/KG`**, 均限重 ≤500g、货值 ≤1500 卢布(超限自动标为不可用), 无赔偿/退回, 自提点取货。见 `references/rates.md`。
4. **跨境国际代理服务费** — 货件价值 **0.33%**, 无封顶, 2026-09-01 起所有跨境订单收, 签收后扣。

**关键提醒**: 2% 与 0.33% 极易漏算(尤其 ZTO 的 2% 代理费)。评分组与佣金档都随**货值(卢布)**跳变, 下单日汇率变化可能让商品跨档, 需用当天汇率复核。利润为单件毛利, 未含退货/退款损耗、促销折价、国内头程运费, 需要时单独说明。

## 参考

- 评分组规则、ZTO / OGL 费率表、佣金档与来源: [references/rates.md](references/rates.md)。

## 维护

- 汇率、费率(尤其 0.33% 生效口径)会随 Ozon 更新变化, 使用前如遇官网改版, 先核对 `references/rates.md` 里的来源链接再沿用。
- 推荐售价为二分近似(取整到元), 跨档商品以脚本输出为准。
