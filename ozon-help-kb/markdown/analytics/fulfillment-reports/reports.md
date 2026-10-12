---
title: "报告"
path: /analytics/fulfillment-reports/reports
id: 72445
updated: 2026-09-07 13:04:14
source: https://global-help.ozon.com/zh/analytics/fulfillment-reports/reports?region=CHN
---

您可以在个人中心获取XML或CSV格式的参考报告。

- 转至
**[分析 → 报告](https://seller.ozon.ru/app/analytics/fulfillment-reports)**
 一栏。

- 在所打开页面的左侧窗格中，选择所需的栏目和报告类型（例如，
**商品 →  所有商品及其在Ozon上的可见性**
）。

![](../../images/ca2a01fe300061d6.png)

- 选择您需要数据的时间段。如果其调整记录不可用，则时间段将显示为
**现在**
——您无法更改此时间段。报告将显示在下载时可以访问的数据。
点击
**下载报告**
。
报告将下载到您的电脑上。字段中的内容取决于报告类型。

## 商品

[所有商品及其在Ozon上的可见性](https://seller.ozon.ru/app/analytics/fulfillment-reports)

有关您商品的数据（例如，Ozon ID、描述、价格、佣金、包装尺寸等）。针对于一些字段的注释：

**Ozon Product ID**
 为我们系统中的商品标识符。例如，如果您从Ozon仓库和您自己的仓库出售商品，则该商品的Ozon Product ID会相同。

- **FBO Ozon SKU ID**
 为从Ozon仓库出售的商品标识符（对您不适用）。

- **FBS Ozon SKU ID**
 为从您自有仓库出售的商品标识符。

- **CrossBorder Ozon SKU**
 为从境外出售的商品标识符。

- **Barcode**
 : the barcode printed on the label.

- **Product status**
 为是否可以在Ozon上购买该商品。如果状态为“准备开售”，则该商品无法购买。
[商品状态详情](/products/upload/created-pdp/status/)
。

- **Available in an Ozon warehouse, pcs**
 : the product stock in the warehouse, available for sale. This number does not include reserved products (not applied to you).

- **Reserved, pcs**
 为多少件商品处于“预留”状态。从在Ozon收到订单起，直到将其包装并交付给买家为止，该商品一直处于保留状态。

- **Limit price:**
 为商品当前的售价（在下载报告时，已包含折扣）。如果商品参与促销活动，则显示的是不含活动优惠的价格。

- **Crossed out price, RUB:**
 为未计算折扣的价格。

- **Recommended price, RUB**
 为该商品在其他电商平台的最低价格。

- **Current link to the recommended price**
 为其他交易平台上最低价相同商品的可用链接。

## 订单

[从我仓库发出的商品](https://seller.ozon.ru/app/analytics/fulfillment-reports)

> > 我们已对发货时间设置了限制。现在最大的时长为一个月。要想查看数月内的订单，请创建多个报告。
>

报告包含由您自有仓库处理的订单及其状态。针对于一些字段的注释：

- **Shipment ID**
 为与订单相关的快递号。订单可以由多个包裹组成。

- **Status**
  为订单状态。

- **Cost**
 为按数量计算的商品总价（金额=最高价格×数量)。

- **Ozon ID**
 为Ozon商品的标识符。

- **Product ID**
 为您的商品代码。

- **Price**
 为商品的有效出售价。

- **Quantity**
 为按该价格出售的商品总件数。

订单状态：

- **存在纠纷**
 订单存在纠纷。
[更多关于有争议订单的信息](/fulfillment/rfbs/logistic-settings/order-management/)
.

- **等待发货**
 订单已配货并正在等待交付至物流公司。

- **等待备货**
 买家已在Ozon网站上下单，订单已被商家接收处理。

- **已取消**
 订单已被取消（原因不限）

- **已签收**
 买家已签收商品。

- **运输中**
 订单已配货完毕并已交付给物流公司。

- **未接受**
 商品未到达分拣中心。若您确信已将商品发运给我们，
[则可提出纠纷](/fulfillment/rfbs/logistic-settings/order-management/)
。

## 退货

[退回至我仓库的商品](https://seller.ozon.ru/app/returns/fbs)

该报告包含有关已签收、准备签收或已退回给您的买家退货商品的相关信息。仅适用于从您自有仓库发出的商品。针对于一些字段的注释：

- **Returned item ID**
 退货商品的标识符。

- **Shipment ID**
 我们系统中的包裹标识符。

- **Status**
 退货状态。

- **Product ID**
 为您的商品代码。

- **Ozon ID**
 我们系统中的商品标识符。

- **Reason for return**
 不得不退货的原因，或买家为什么拒绝该商品。

- **Placement cost**
 因将退货商品存放于取件点而产生的费用。

- **Changed to Ready for pickup**
 退货商品被存放于取件点的起始日期。

- **Last day of free placement**
 退货商品可以免费存放于取件点的最终日期。自第二天起，存放服务将收取费用。

- **Date returned to merchant**
 商品送达至您手上的时间。

- **Location**
 退货商品所在取件点的名称。

- **Package opened**
 若买家在退货之前已拆开包装，则该行将显示“是”。

- **Referral fee percentage**
 以百分点计的商品销售佣金率。它在买家下单时就已固定。
[佣金详情](/commissions/ozon-fees/commissions/)

- **Referral fee (RUB)**
 按商品价格计算的Ozon销售佣金额（卢布)。

- **Price w/o referral fee (RUB)**
 商品价格减去佣金（不含佣金的价格=商品价格–佣金)。

退货状态：

- **Received from the buyer**
 买家已向我们退回不适合他的商品。

- **Ready to pickup**
 退货商品已到达取件点供您取件。取件点已在“所在位置”一列中注明。

- **Received**
 退货商品已送至您手上。

## 应计额

[报告期内的应计额和佣金](https://seller.ozon.ru/app/analytics/fulfillment-reports)

该报告包含报告期内的相关应计额和佣金额。针对于一些字段的注释：

- **报告期起始日**
 报告期的开始日期。

- **报告期结束日**
 报告期的结束日期。

- **期初余额**
 您在报告期开始时的余额。

- **期末余额**
 您在报告期结束时的余额。

- **订单总额**
 该期内所交付商品的货款总额。

- **退款总额**
 该期内退还给您的商品的总金额。

- **佣金**
 Ozon进行订单或退货处理所收取的佣金（卢布)。

- **附加服务**
 在该期内向您提供的附加服务总额（例如，Ozon上的商品促销服务或因将商品存放于取件点而产生的费用)。

- **增值税总额**
 增值税的总金额。

[与交易相关的应计额和佣金](https://seller.ozon.ru/app/analytics/fulfillment-reports)

该报告包含已签收、取消或退回商品的相关应计额和佣金。这些数据根据具体的商品进行提供。针对于一些字段的注释：

- **Operation date**
 将订单或退货相关款项汇至您账户上的日期。

- **Operation type**
 将商品送至买家或退给合作伙伴。

- **Vendor product code**
 您系统中的商品代码。

- **Selling price**
 订单或退货商品的价格。

- **Referral fee rate**
 Ozon因处理订单或退货所收取的佣金（以百分点计），取决于商品类别。

- **Quantity**
 以该同一价格出售或退货的商品数量。

- **Operation amount**
 按商品数量计算的销售总额（交易总额=售价×数量)。

- **Ozon referral fee**
 Ozon进行订单或退货处理所收取的佣金（卢布)。

- **Operation amount excluding the referral fee**
 您将收到的订单销售额。退货情况下，该金额为负数。

- **Warehouse of shipping**
 订单的起运地点：Ozon仓库或是您的自有仓库。

## 质量把控

[取消率](https://seller.ozon.ru/app/analytics/fulfillment-reports)

该报告包含的数据涉及最近7天内的所有包裹，以及该期内您所取消包裹所占的比例。针对于一些字段的注释：

- **Accepted for processing**
 包裹被接收处理的日期和时间。其中显示了在最近7天内处理的包裹。

- **Shipment cancelled**
 包裹是否已被取消（原因不限）。

- **Cancelled by the merchant**
 包裹是否已被您取消（原因不限）。

- **Cost**
 包裹所含商品的总价值是多少？

- **Accounted for in the numerator**
 在计算取消率时，包裹是否已被算入分子中。

- **Accounted in the denominator**
 在计算取消率时，包裹是否已被算入分母中。.

- **Cancellation percentage in the number of shipments**
 您在最近7天内取消的包裹所占的比例。

**Numerator**
 您在最近7天内取消的包裹总数。
**Denominator**
 在最近7天内所创建的包裹总数。
**Cancellation percentage in shipment costs**
 您在最近7天内取消的包裹所占的比例。

**Numerator**
 您在最近7天内取消的包裹所含商品的总价值。
**Denominator**
 在最近7天内创建的包裹所含商品的总价值。
[逾期交货](https://seller.ozon.ru/app/analytics/fulfillment-reports)

该报告包含最近14天所有包裹的相关数据，以及在该期内因您过错而未按时交付给物流公司的包裹所占的比例。针对于一些字段的注释：

**Accepted for processing**
 包裹被接收处理的日期和时间。其中显示了在最近14天内处理的包裹。

- **Shipment date**
 包裹的发货日期。仅含最近14天以内的日期。

- **Shipment cancelled**
 包裹是否已被取消（原因不限）。

- **Cancelled before shipment date**
 您将包裹交付给快递员或收货点之前它是否已被取消。

- **Delay of shipment through the merchant's fault**
 您是否已逾期发货（配货时长不得超过24个小时)。

- **Delay in calendar days**
 您逾期发货的延误天数。

- **Accounted in the numerator**
 在计算逾期交货率时，包裹是否已被算入分子中。

- **Accounted in the denominator**
 在计算逾期交货率时，包裹是否已被算入分母中。
**Percentage of non-handed-over shipments**
 最近14天内因您过错而未按时交付给物流公司的包裹所占的比例。

**Numerator**
 您在最近14天内未交付给物流公司的包裹数量。
**Denominator**
 您在最近14天内应当交付给物流公司的包裹数量。
