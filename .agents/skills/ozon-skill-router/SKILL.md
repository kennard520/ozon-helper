---
name: ozon-skill-router
description: 在 ozon-helper 项目内执行 Ozon 业务任务（选品/利润/商品卡/数据/图片/知识库等）时，用于选用全局豆包 Skill 的路由表。触发：用户在本项目中提出 Ozon 相关任务，需要配合全局豆包能力（选品、文案、数据分析、图表、文档交付、浏览器自动化、定时任务等）时，先读本 skill 再决定调用哪些全局 skill。
---

# ozon-helper 全局豆包 Skill 路由表

本项目业务闭环的主流程由项目级自定义 skill 承担（`.agents/skills/` 下的 scout、ozon-profit-calculator、ozon-card、ozon-desc、ozon-product-kit、ozon-stats、oss-upload、ozon-help-sync）。本路由表定义每个业务环节应**配合调用**哪些全局豆包 skill，避免重复造轮子并统一口径。

## 路由总览

| 业务环节 | 主流程（项目 skill） | 配合的全局 skill | 使用要点 |
|---|---|---|---|
| 选品调研 | scout | doubao-product-selection、doubao-market-hotspot | 选品结论可交叉 doubao-product-selection 的筛选维度；doubao-market-hotspot 用于判断品类/平台事件风险 |
| 利润核算 | ozon-profit-calculator | （无） | 只算 Ozon 平台佣金 + 物流（ZTO/OGL/China Post），**不涉及税**，勿接税务类 skill |
| 商品内容生成 | ozon-product-kit / ozon-card / ozon-desc | doubao-listing-localization、doubao-cross-border-growth-content、doubao-product-content | 全局 skill 提供俄语本地化与跨境卖点素材；最终卡片合规以 ozon-card 的规则为准 |
| 商品图设计 | ozon-product-kit（image_gen / image_edit） | doubao-creative-design（含 seedream-50） | 出图前按 doubao-creative-design 走设计交付流程；图片规格（3:4、无中文、无价格、图片总数≥6张等）以 ozon-product-kit 的"Ozon 图片要求"章节为准 |
| 图片上传托管 | oss-upload | （无） | 纯工程环节 |
| 店铺数据监控 | ozon-stats | sheet、doubao-data-analysis、doubao-visualization | 清单/导出用 sheet；指标异动归因用 doubao-data-analysis；日报与图表用 doubao-visualization |
| 帮助知识库维护 | ozon-help-sync | html、lark-doc、doubao-enterprise-search | 知识库内容检索用 doubao-enterprise-search；发布/交付载体用 html 或 lark-doc |
| 客服/售后 | （项目内处理） | doubao-customer-service | 生成客户消息处理方案与话术 |
| 评论/舆情 | （项目内处理） | doubao-sentiment-tracker | 商品评论、店铺口碑追踪与溯源 |
| 营销活动 | （项目内处理） | doubao-ecommerce-proposal、doubao-marketing-plan、doubao-headlines-calendar、doubao-newmedia-writing、doubao-multiplatform-rewrite、doubao-marketing-material-review | 活动策划、营销日历、站外内容、多平台改写、物料合规审查 |
| 定时任务 | （项目内处理） | doubao-cron-scheduler | 定时抓数、定时提醒、后台监控 |
| 工程与交付支撑 | （项目内处理） | browser-use-automation、browser-record-replay、computer-use-automation、doubao-app-builder、verifier-hub、artifact-preview | Ozon 后台/反爬页面操作、看板类小工具、交付前验证 |

## 使用规则

1. 主流程一律走项目级 skill；全局 skill 只做素材补充、分析、交付与自动化，不得绕过项目级 skill 的合规口径。
2. **上架通道硬性禁止**：任何 Ozon 商品上架**禁止使用 `/v1/product/import-by-sku`（copy_by_sku / 复制上架通道）**——竞品多开禁止复制，且跨境店复制会被审核拦截；一律走 `/v3/product/import` 原创建卡（配合 ozon-product-kit 生成的图片/文案资产）。本规则优先级高于一切执行便利性考量。
3. 规则冲突时以项目级 skill 为准：如 ozon-product-kit 的图片硬性要求、ozon-card 的卡片合规、ozon-profit-calculator 的成本口径。
4. 利润核算不接税务/合规类 skill（佣金+物流已由 calc_profit.py 覆盖）；若未来需要进口税/VAT 测算，单独评估。
5. 明确不接入的全局 skill 类别：学术论文类、医疗健康类、豆包自身产品类（doubao-identity、学生优惠、礼品卡）、个人理财/股票推荐类、小说/游戏/专利创作类。
6. 完整接入矩阵与触发说明见 `E:\personal\ozon-helper\docs\skill-integration.md`。