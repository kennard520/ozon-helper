---
title: "使用API"
path: /api/intro
id: 72447
updated: 2026-07-31 13:12:07
source: https://global-help.ozon.com/zh/api/intro?region=CHN
---

Ozon Seller API是程序 接口 ，用于 对接   Ozon市场平台。 它可让Ozon与卖家系统交换信息，并帮助自动执行日常操作。

例如，借助Ozon Seller API方法，您可以：

- 上传和更新商品；

- 管理商品价格和库存；

- 获取商品退货信息；

- 管理FBS和rFBS模式下的订单；

- 管理聊天；

- 处理运单；

- 获取财务和分析信息；

- 获取属性和特征数据。

[了解更多关于Ozon Seller API的信息](https://docs.ozon.ru/api/seller/zh/#tag/Getting-started)

## 使用API

出于安全考虑，Seller API使用API密钥进行身份验证，以确认请求的真实性。 操作流程包括发送请求和接收响应。

为此，您可以使用
[Seller API文档](https://docs.ozon.ru/api/seller/zh/#tag/Getting-started)
中的
**控制台**
选项卡、
[Postman](https://www.postman.com/)
，或设置与业务管理系统的集成，例如1C、ERP或MoySklad。

[如何通过控制台测试方法](#测试方法)

### 获取API密钥

> > 请勿将API密钥提供给无关人员。
>

- 在个人中心中，前往
[设置 → 卖家 API](https://seller.ozon.ru/app/settings/api-keys)
。

- 点击
**生成密钥**
 。

![](../images/e82a071f6b49055f.png)

- 为密钥命名并选择角色，即访问权限级别。
点击
**生成**
。
每个API密钥只能根据所选角色使用特定方法。 您可以创建多个API密钥，例如，当您有多个不同访问权限级别的用户时。

### 指定用于管理店铺的IP地址范围

进入API密钥设置：点击
![](../images/04a41c62a8a0b548.png)
**→ 编辑**
。

- 在
**允许网络**
模块中点击
**添加网络**
。

- 输入网络名称。在“地址”字段中，以CIDR表示法填写地址范围。

- 请保存更改。

### 测试方法

如需执行请求：

- 在方法卡片中，进入
**控制台**
选项卡。
点击  并填写字段：

**Client ID**
——卖家 标识符;
**Api-Key**
——API密钥。
填写请求体。
点击
**发出请求**
。

![](../images/5d65720096335640.png)

如果您有任何问题，请通过个人中心联系客服。
