# ozon-helper 全局豆包 Skill 接入矩阵

> 更新：2026-10-12・状态：已落地（路由表 
>
> `.agents/skills/ozon-skill-router/SKILL.md`
>
>  \+ 本矩阵）
> 口径修正：利润核算环节
>
> **不接**
>
>  
>
> `doubao-ecommerce-compliance-tax-logistics`
>
> （ozon-profit-calculator 只算 Ozon 平台佣金 + 物流费，不含税；该 Skill 面向进口税 / VAT / 关税类核算，本项目暂不需要）。

## 一、接入方式说明

全局豆包 Skill 已预装在豆包工作区，**无需安装**——agent 在任务中按关键词自动发现并调用。所谓 "接入"，是把它们与本项目业务环节绑定、固化使用约定，让后续每次会话都按同一套口径执行：



1. 路由 Skill：`.agents/skills/ozon-skill-router/SKILL.md` —— 业务环节 → 全局 Skill 的路由表（agent 自动读取）；

2. 本矩阵文档：业务环节、触发场景、使用要点的完整说明；

3. `AGENTS.md` 已追加 "Skill 使用指引" 小节，指向以上两处。

## 二、接入矩阵

### A. 核心（直接命中主业务，优先使用）



| 业务环节  | 项目主流程                 | 全局 Skill                             | 触发场景                    | 说明                                   |
| ----- | --------------------- | ------------------------------------ | ----------------------- | ------------------------------------ |
| 选品调研  | scout                 | doubao-product-selection             | "这个品能做吗"" 帮我筛一批品 "      | 交叉选品维度，补充 scout 的结论                  |
| 选品风险  | scout                 | doubao-market-hotspot                | "XX 事件对品类有没有影响"         | 平台 / 市场事件 → 品类影响判断                   |
| 商品内容  | ozon-card / ozon-desc | doubao-listing-localization          | "俄语标题怎么起""listing 本地化 " | 俄语本地化表达                              |
| 商品内容  | ozon-card / ozon-desc | doubao-cross-border-growth-content   | "写详情页卖点"" 增长文案 "        | 跨境卖点、证据化内容                           |
| 商品内容  | ozon-card / ozon-desc | doubao-product-content               | "生成商品描述"                | 商品内容素材                               |
| 商品图   | ozon-product-kit      | doubao-creative-design（+seedream-50） | "生成商品图 / 主图 / 场景图"      | 出图前走设计交付流程；硬性要求以 ozon-product-kit 为准 |
| 数据报表  | ozon-stats            | sheet                                | "导出清单"" 做表 ""算个账"       | 项目根目录大量 CSV 清单、报表交付一律走 sheet         |
| 数据分析  | ozon-stats            | doubao-data-analysis                 | "曝光为什么跌"" 哪个品贡献大 "      | 指标异动归因、漏斗分析                          |
| 数据可视化 | ozon-stats            | doubao-visualization                 | "做个日报图"" 趋势图 "          | 图表 / 信息图 / HTML 可视化                  |
| 文档交付  | —                     | html / word / lark-doc               | "出报告"" 写文档 "            | 报告、正式文书、在线文档载体                       |

### B. 运营辅助（按需启用）



| 全局 Skill                         | 触发场景                             |
| -------------------------------- | -------------------------------- |
| doubao-sentiment-tracker         | 商品评论、店铺口碑追踪（微博 / 知乎 / B 站 / 抖音等） |
| doubao-cron-scheduler            | 定时抓数据、定时提醒、后台监控                  |
| doubao-customer-service          | 客户消息、售前售后、催发货、退换货话术方案            |
| doubao-ecommerce-proposal        | 店铺活动策划方案                         |
| doubao-marketing-plan            | 营销计划                             |
| doubao-headlines-calendar        | 营销日历 / 节点选题                      |
| doubao-newmedia-writing          | 公众号 / 小红书等中文新媒体内容                |
| doubao-multiplatform-rewrite     | 同一内容多平台改写                        |
| doubao-marketing-material-review | 营销物料 / 详情页合规审查                   |

### C. 工程与交付支撑



| 全局 Skill                                       | 触发场景                                                        |
| ---------------------------------------------- | ----------------------------------------------------------- |
| browser-use-automation / browser-record-replay | Ozon 后台页面操作、帮助中心反爬抓取（ozon-help-sync 依赖浏览器内 fetch）、录制可复用 RPA |
| computer-use-automation                        | 桌面级自动化操作                                                    |
| doubao-app-builder                             | 管理看板、选品小工具等网页应用                                             |
| verifier-hub / artifact-preview                | 交付前对 xlsx/docx/pdf/pptx 等产物做确定性验证与预览                        |
| doubao-enterprise-search                       | 检索项目内部知识、历史记录、会议纪要                                          |

### D. 可选（一般用不到，出现明确场景再启用）



| 全局 Skill                                                       | 场景                               |
| -------------------------------------------------------------- | -------------------------------- |
| doubao-public-company-analysis / multi-stock-comparison        | 分析 OZON 平台（NASDAQ:OZON）及供应商公司基本面 |
| doubao-industry-analysis                                       | 跨境电商行业分析                         |
| doubao-contract-reviewer / doubao-compliance-assessment-public | 供应商合同、平台协议审查                     |
| lark-base / lark-im / lark-calendar                            | 飞书多维表格台账、群通知、日程协作                |

### E. 明确不接入

学术论文类、医疗健康类、豆包自身产品类（doubao-identity、student-discount-application、gift-card-redemption）、个人理财 / 股票推荐类（doubao-wealth-planning、doubao-stock-screening、doubao-daily-stock、doubao-earnings-analysis）、小说 / 游戏 / 专利 / 问卷等创作类、doubao-pc-optimizer 等与本项目无关的类别。

## 三、使用约定



1. 主流程一律走项目级 skill；全局 skill 只补充素材、分析、交付与自动化，不得绕过项目级合规口径。

2. 冲突时以项目级 skill 为准：ozon-product-kit 图片硬性要求、ozon-card 卡片合规、ozon-profit-calculator 成本口径。

3. 利润核算不接税务 / 合规类 skill；若未来需要进口税 / VAT 测算，再单独评估后更新本矩阵。

4. 新增业务环节时，先更新 `.agents/skills/ozon-skill-router/SKILL.md` 路由表，再同步本矩阵。