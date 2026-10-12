---
title: "货币多样性"
path: /accounting/receiving-payments/multicurrency
id: 72417
updated: 2026-09-16 12:02:13
source: https://global-help.ozon.com/zh/accounting/receiving-payments/multicurrency?region=CHN
---

从2022年9月1日起，外国卖家的定价原则正在发生变化：现阶段，在上传商品时，有必要以合同规定的货币标明商品的价格。 价格将自动转换为卢布，因此，这对俄罗斯买家不会有任何变化。

> > 更改不适用于来自白俄罗斯、哈萨克斯坦、吉尔吉斯斯坦、乌兹别克斯坦、塔吉克斯坦、亚美尼亚，阿塞拜疆和摩尔多瓦的卖家。
>

## 货币选择

货币结算是在个人账户的注册阶段时选择的。 之后，您将无法更改货币。 所选货币固定在与Ozon的合同中，并在
[设置→银行详细信息和合同→合同](https://seller.ozon.ru/app/settings/contracts)
 部分的个人信息中心中.

![](../../images/b098d18898ad7786.png)

可用货币列表取决于您所在的国家/地区:

- 中国 — CNY；

- 土耳其 — USD/RUB；

- [欧 洲](https://cdn.ozone.ru/s3/ozon-disk-api/techdoc/global/attachments/launch/可以用EUR和RUB来支付的欧洲国家列表_1665570548.pdf)
 — EUR / RUB；

- 白俄罗斯 – BYN/RUB;

- 哈萨克斯坦 – KZT/RUB;

- 吉尔吉斯斯坦 – KGS;

- 亚美尼亚 – RUB;

- 其他 — USD/RUB。

要以其他货币接收付款，请创建一个新的个人信息中心并为其选择所需的货币。 ##上传商品

只有在注册、接受要约、激活个人中心后才可以上传商品。 上传商品后，我们将商品价格从您的合同货币转换为卢布。 商品的卢布价格取决于您的货币对卢布的汇率。 例如，如果商品的成本为10美元，那么在1美元=59.9608RUB的汇率下，考虑到四舍五入，其价格将为600卢布。 在1美元=60.2472RUB的汇率下，该产品将花费602卢布。

上传商品时，在
[个人中心](/zh-hans/products/upload/upload-types/account/)
 中请用合同货币指定商品的价格。

![multicurrency_1_cn](../../images/c1268ee51ce60380.png)

在上传商品时
[用模板](/zh-hans/products/upload/upload-types/xls/#%e5%a6%82%e4%bd%95%e5%a1%ab%e5%86%99%e6%a8%a1%e6%9d%bf)
 在模板中以合同的货币指定商品价格。

![multicurrency_cn_2](../../images/5b376009b967f9e4.png)

上传商品时
[通过Seller API](/zh-hans/api/via-api/)
 指定合同的
[货币代码](#货币代码)
以及合同货币的商品价格。除卢布以外的合约货币必须从9月1日起在 "currency_code" 字段中指定。

以下Seller API方式必须填写 "currency_code" 字段:

- [POST/v2/product/import](https://docs.ozon.ru/api/seller/en/#operation/ProductAPI_ImportProductsV2)
,

- [POST/v1/product/import/prices](https://docs.ozon.ru/api/seller/en/#operation/ProductAPI_ImportProductsPrices)
,

- [POST/v1/product/import-by-sku](https://docs.ozon.ru/api/seller/en/#operation/ProductAPI_ImportProductsBySKU)
。

您可以通过以下Seller API方式获取currency_code:

- [POST/v3/posting/fbs/get](https://docs.ozon.ru/api/seller/en/#operation/PostingAPI_GetFbsPostingV3)
,

- [POST/v3/posting/fbs/list](https://docs.ozon.ru/api/seller/en/#operation/PostingAPI_GetFbsPostingListV3)
,

- [POST/v3/posting/fbs/unfulfilled/list](https://docs.ozon.ru/api/seller/en/#operation/PostingAPI_GetFbsPostingUnfulfilledList)
,

- [POST/v3/posting/fbs/ship](https://docs.ozon.ru/api/seller/en/#operation/PostingAPI_ShipFbsPostingV3)
,

- [POST/v4/posting/fbs/ship](https://docs.ozon.ru/api/seller/en/#operation/PostingAPI_ShipFbsPostingV4)
,

- [POST/v4/product/info/prices](https://docs.ozon.ru/api/seller/en/#operation/ProductAPI_GetProductInfoPricesV4)
,

- [POST/v2/product/info](https://docs.ozon.ru/api/seller/en/#operation/ProductAPI_GetProductInfoV2)
,

- [POST/v2/product/info/list](https://docs.ozon.ru/api/seller/en/#operation/ProductAPI_GetProductInfoListV2)
。

如果您的合同货币为RUB（俄罗斯卢布），则无需填写 “currency_code” 字段。如果该字段留空，价格将自动设置为 RUB（俄罗斯卢布）。

### 货币代码

- RUB — 俄罗斯卢布，

- EUR — 欧元，

- CNY — 元。

## 参与促销的产品价格

从 2022 年 9 月 1 日起，所有促销金额必须按照您合同中指定的货币显示。

### 当前促销

将价格转换为合同货币时，您的促销活动将被删除，因此您需要重新创建它们。您可以在
[我的促销](https://seller.ozon.ru/app/highlights/my-highlights/create)
 部分、个人中心中创建促销。

来自 Ozon 的促销活动可在您的中心中的
[价格和促销活动 → 来自Ozon的促销活动](https://seller.ozon.ru/app/highlights/list)
。促销期间的价格必须以您的合同中指定的货币显示。
