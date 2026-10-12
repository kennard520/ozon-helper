# Ozon 跨境(RFBS)费率口径与来源

> 供 `calc_profit.py` 使用与日后更新核对。均以卢布计、按**货件价值**与**重量**定档, 中国卖家(region=CHN)口径。

## 一、销售佣金(汽车用品 Car Products, RFBS)

| 货件价值(卢布) | 佣金率 |
|---|---:|
| ≤1500 | 12% |
| 1501–5000 | 17% |
| >5000 | 17% |

> 来源: Ozon 中国佣金表 `Tarifs_CN_01_12_2025`(sheet "MP Tree Tarifs CN", 列 6–8 = RFBS 三档)。
> 本地副本: `C:\Users\zqr\Desktop\thinkcar\commissions_table.xlsx`。

## 二、评分组(决定运费档)

按 **货件价值(卢布) + 计费重量(g)** 划档; Big / Premium Big 按体积重(长×宽×高 cm ÷ 12)。

| 价值(卢布) | 重量(g) | 评分组 |
|---|---:|---|
| 1–1500 | ≤500 | Extra Small |
| 1–1500 | 501–30000 | Budget |
| 1501–7000 | ≤2000 | Small |
| 1501–7000 | 2001–30000 | Big |
| 7001–250000 | ≤5000 | Premium Small |
| 7001–250000 | 5001–30000 | Premium Big |

> 来源: Ozon 帮助中心《OGL 费率》与《合作物流费率》文章 + 项目内 `realfbs_routes_seed.json`。

## 三、ZTO(合作物流) Standard 档费率(fix + var/g, 人民币)

| 评分组 | fix | var/g |
|---|---:|---:|
| Extra Small | 3.12 | 0.0364 |
| Budget | 23.92 | 0.026 |
| Small | 16.64 | 0.0364 |
| Big | 37.44 | 0.026 |
| Premium Small | 22.88 | 0.0364 |
| Premium Big | 64.48 | 0.02912 |

> Express / Economy 档 var 不同, 见项目 `apps/webui/src/webui/realfbs_routes_seed.json`。ZTO 成都仓 PUDO/Courier。

## 四、OGL(Ozon Global Logistics) 运输服务费(fix + var/g, 人民币)

| 评分组 | fix | var/g |
|---|---:|---:|
| Extra Small | 2.9 | 0.0247 |
| Budget | 22.25 | 0.0164 |
| Small | 15.48 | 0.0242 |
| Big | 34.82 | 0.0164 |
| Premium Small | 21.28 | 0.0242 |
| Premium Big | 59.97 | 0.0222 |

> 来源: Ozon 帮助中心《OGL 费率》文章 + OGL 费率表 `OGL_ENG_CN_24_08_26_added_Pick-up.xlsx`(本地副本 `C:\Users\zqr\Desktop\thinkcar\ogl_rates.xlsx`)。OGL 费用比合作物流 Economy 低约 14%。

## 四点五、China Post to PUDO(邮政, 用户提供 Ozon 物流产品表)

| 产品 | 代码 | 方式 | 重量区间 | 费用 | 限制 |
|---|---|---|---|---|---|
| WH 陆运 · China Post to PUDO Economy | 214215220200791 | 陆运 | 1g–500g | **1.9元/件 + 26元/KG** | 货值≤1500 卢布; 无赔偿/退回; 自提点取货; 尺寸三边≤90cm |
| WH 航空 · China Post to PUDO Standard | 214215200011791 | 空运 | 1g–500g | **1.9元/件 + 67元/KG** | 货值≤1500 卢布; 无赔偿/退回; 自提点取货 |

> - 两者已在 `calc_profit.py` 中实现(渠道键 `china_post`=陆运, `china_post_air`=空运); 超限重(>500g)或超货值(>1500R)时该渠道自动标为不可用。
> - 同样适用 2% Ozon 代理费 + 0.33% 跨境代理费(属合作物流渠道)。

## 五、物流上的两笔附加费(极易漏算)

| 项目 | 规则 | 适用 |
|---|---|---|
| Ozon 电子服务/代理费 | 货件价值 × **2%**, 每件封顶 **15~200 卢布** | ZTO / OGL / China Post 都收 |
| 跨境国际代理服务费 | 货件价值 × **0.33%**, 无封顶, 签收后扣 | 2026-09-01 起**所有跨境订单**, 三渠道都收 |

> 来源: 知识库文章
> - `markdown/commissions/ozon-fees/partner-delivery-rates.md`(合作物流含 2% 代理费)
> - `markdown/commissions/ozon-fees/ogl-rates.md`(OGL 含 2% 电子服务)
> - `markdown/commissions/ozon-fees/commissions-for-other-services.md`(国际运输组织合同签订服务 = 跨境国际代理服务费 0.33%, 2026-09-01 生效)

## 六、汇率

`--rate` 默认 **12.7154**(1 CNY = 12.7154 RUB, 2026-10-09 新浪收盘; 交易实时 12.7259)。下单日以**当天俄罗斯央行交叉汇率**为准, 跨档商品务必复核。

## 七、本地参考数据

- 项目 ZTO 种子: `E:\personal\ozon-helper\apps\webui\src\webui\realfbs_routes_seed.json`(141 条, 含各物流商各档费率)
- 内置定价服务: `apps/webui/src/webui/services/_pricing.py`
- 测试 fixture `apps/webui/tests/fixtures/calc_sample.json` 为**测试数据, 非真实费率**
