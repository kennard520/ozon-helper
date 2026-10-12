---
title: "“为您的商品快速收集评价”新品广告活动"
path: /work-with-customers/points-for-reviews/for-new-products
id: 76260
updated: 2026-10-09 09:16:01
source: https://global-help.ozon.com/zh/work-with-customers/points-for-reviews/for-new-products?region=CHN
---

| [“快速收集评价”的工作原理](https://global-help.ozon.com/zh/work-with-customers/points-for-reviews/points-algorithm) | [“快速收集评价”手动广告活动](https://global-help.ozon.com/zh/work-with-customers/points-for-reviews/manual) | **“为您的商品快速收集评价”新品广告活动** | [自动精选商品集](https://global-help.ozon.com/zh/work-with-customers/points-for-reviews/auto-collections) |
| --- | --- | --- | --- |

“为您的商品快速收集评价”是一项广告活动，会自动将新的商品卡片接入“快速收集评价”，帮助它们更快获得首批评价。这些商品会添加到
**“为您的商品快速收集评价”**
列表中，该列表位于
**[商品 → 快速收集评价](https://seller.ozon.ru/app/reviews/promotions)**
部分。

**广告活动默认参数：**

- 没有时间限制；

- 每条评价适用固定出价；

- 收集评价数量为10条。

在此类广告活动中，无法管理广告活动周期，但可以更改收集评价数量或删除商品：

- 更改评价数量——在
**[商品 → 快速收集评价](https://seller.ozon.ru/app/reviews/promotions)**
页面打开
**“为您的商品快速收集评价”**
广告活动，选择所需商品，然后点击
**设置评价数量**
。填写所需的评价数量，但不得少于10条，然后点击
**应用。**

- 删除商品——在
**[商品 → 快速收集评价](https://seller.ozon.ru/app/reviews/promotions)**
页面打开
**“为您的商品快速收集评价”**
广告活动，选择所需商品，然后点击
**删除**
。

您也可以关闭将商品自动添加到
**“为您的商品快速收集评价”**
广告活动中的功能。

> > 如果您的余额变为负数，我们可能会暂停收集评价活动，并关闭移动应用中收集评价功能的访问权限。
>

## 管理商品接入“为您的商品快速收集评价”广告活动

> > 您可以在
> **[商品 → 商品卡片管理](https://seller.ozon.ru/app/items/transfer)**
> 部分的
> **将新商品添加到“快速收集评价”中**
> 模块中管理新品接入该工具：
> - 将开关保持为开启状态，以便自动将商品添加到“快速收集评价”；
> - 将开关切换为关闭状态，以关闭商品自动添加到“快速收集评价”的功能。

![Screen 1 cn](../../images/bf00418d75b0f848.png)

> > 所有已接入该广告活动的商品都会汇总在
> **“为您的商品快速收集评价”**
> 列表中，该列表位于
> **[商品 → 快速收集评价](https://seller.ozon.ru/app/reviews/promotions)**
> 部分。
>

| **已开启商品自动添加到“快速收集评价”** | **已关闭商品自动添加到“快速收集评价”** |
| --- | --- |
| 如果在
**[商品 → 商品卡片管理](https://seller.ozon.ru/app/items/transfer)**
部分已开启
**将新商品添加到“快速收集评价”中，**
则所有新品都会自动接入“快速收集评价”
**。**
如有需要，您可以在创建商品卡片时为特定商品
**关闭**
快速收集评价：
[手动](https://global-help.ozon.com/zh/products/upload/upload-types/account)
——取消勾选“快速收集评价”模块中的复选框；
![Screen 2.1 cn](../../images/62f503cb15579587.png)
[通过XLS模板](https://global-help.ozon.com/zh/products/upload/upload-types/xls)
——在“付费推广”模块的“快速收集评价”列中输入
**否**
。如果该字段留空，我们会将商品添加到广告活动中；
![Screen 3.1 cn](../../images/d6b41e74f6b2aec6.png)
[通过在线表格](https://global-help.ozon.com/zh/products/upload/upload-types/online-sheets)
——在“付费推广”列中不要选择“快速收集评价”工具；
![Screen 4.1 cn](../../images/a89a6712e33822f6.webp)
通过API——在/v3/product/import方法中，字段“reviews_promo”负责广告活动类型。填写
**disable，**
即可关闭广告活动。
[Seller API文档中的更多信息](https://docs.ozon.ru/api/seller/zh/)
通过复制创建商品时，无法关闭商品参与广告活动。 | 如果在
**[商品 → 商品卡片管理](https://seller.ozon.ru/app/items/transfer)**
部分已关闭
**将新品添加到“快速收集评价”**
，则不会自动将新品接入“快速收集评价”
**。**
如有需要，您可以在创建商品卡片时为特定商品
**开启**
快速收集评价：
[手动](https://global-help.ozon.com/zh/products/upload/upload-types/account)
——在“付费推广”模块的“快速收集评价”字段中勾选复选框；
![Screen 2.2 cn](../../images/6ee98fbe5474aaee.png)
[通过XLS模板](https://global-help.ozon.com/zh/products/upload/upload-types/xls)
——在“付费推广”模块的“快速收集评价”列中设置值
**是；**
![Screen 3.2 cn](../../images/2534d0341368e421.png)
[通过在线表格](https://global-help.ozon.com/zh/products/upload/upload-types/online-sheets)
——在“付费推广”列中设置值
**快速收集评价**
。
![Screen 4.2 cn](../../images/004747a7623dbc97.webp)
通过API——在/v3/product/import方法中，字段“reviews_promo”负责广告活动类型。填写
**enable**
，即可开启广告活动。
[Seller API文档中的更多信息](https://docs.ozon.ru/api/seller/zh/) |

## 从“为您的商品快速收集评价”广告活动中删除所有商品

无法关闭
**“为您的商品快速收集评价”**
广告活动本身。您可以从该广告活动中排除所有商品。为此：

- 在
**[商品 → 快速收集评价](https://seller.ozon.ru/app/reviews/promotions)**
部分打开
**“为您的商品快速收集评价”**
广告活动。

- 勾选
**SKU**
列，并在底部面板点击
**全选**
，然后点击
**删除**
。

![Group 2 кит](../../images/ab918bb0ff47eba8.webp)

之后，我们将停止激励买家为您的商品留下评价。如果订单是在促销活动期间创建的，并且该订单的评价在买家收到商品后的5天内出现，将按促销活动资费扣款。此类扣款在广告活动关闭后仍可能继续发生，这会考虑配送时间以及5天的评价期限。

**示例**

买家在8月17日创建了订单。您在8月18日关闭了广告活动。如果买家在8月20日收到商品，并在8月24日留下评价，将按促销活动资费扣款：买家收到商品后尚未超过5天，并且商品仍参与广告活动。

[服务费用详情](https://global-help.ozon.com/zh/commissions/ozon-fees/commissions-for-other-services)

##
