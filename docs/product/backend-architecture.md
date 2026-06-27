# 后端 webui 应用层架构

> 2026-06-27/28 绞杀拆分:`app_service.App`(原 3875 行 god-class)+ `main.py`(原 980 行 god-router)按领域拆成 mixin + routers。行为零变化、HTTP 契约不变、714 测试全绿。

## 分层

```
apps/webui/src/webui/
├── main.py                 # 143 行:建 FastAPI app + 中间件/异常 + include_router 装配 + SPA/静态挂载
├── app_instance.py         # APP 单例持有者(main 构造后写入;routers 用活属性引用避免循环 import)
├── app_service.py          # 118 行:class App(13 mixin) 薄 facade,只剩 __init__ + _ensure_auth_bootstrap + helper re-export
├── services/               # 领域逻辑(mixin)
│   ├── _helpers.py         # 模块级纯函数(_to_int/_attr_language/_img_type_from_label/step_flags…)+ 常量
│   ├── _auth.py            # AuthMixin:登录/用户/钱包/presign
│   ├── _settings.py        # SettingsMixin:state/save_settings/多店/AI模型
│   ├── _category.py        # CategoryMixin:类目树/属性字典/required_check/品牌搜/类目识别
│   ├── _drafts.py          # DraftMixin:草稿 CRUD/批量/变体组兄弟
│   ├── _publish.py         # PublishMixin:发布/预检/批量/翻译/拉Ozon商品/变体组发布/FBS标签
│   ├── _ai_card.py         # AiCardMixin:ai_generate/ai_copy/ai_fill_attributes/understand/物理量/proposal/recommend
│   ├── _ai_image.py        # AiImageMixin:出图/候选/图集计划/信息图/富文本/批量
│   ├── _ai_video.py        # AiVideoMixin:Agnes 图生视频
│   ├── _gallery.py         # GalleryMixin:图集增删排序/跨变体复制
│   ├── _ext.py             # ExtMixin:插件桥接/采集/媒体/快照
│   ├── _genjob.py          # GenJobMixin:生图 MQ 任务提交/状态
│   ├── _pricing.py         # PricingMixin:realFBS 路线表/佣金类目
│   └── _warehouse.py       # WarehouseMixin:仓库/FBS/采购/发货
└── routers/                # 每域一个 APIRouter,端点只调 APP
    ├── auth.py settings.py category.py drafts.py publish.py
    ├── ai_text.py ai_image.py ai_video.py gallery.py
    └── ext.py pricing.py warehouse.py
```

## 约定

- **App = 薄 facade,组合 13 个领域 mixin**:`class App(AuthMixin, SettingsMixin, CategoryMixin, DraftMixin, PublishMixin, AiCardMixin, AiImageMixin, AiVideoMixin, GalleryMixin, ExtMixin, GenJobMixin, PricingMixin, WarehouseMixin)`。共享状态(`self.store/catalog/catalog_ru/_cand_lock`)在 `__init__`;mixin 经 `self.` 用,**跨域调用无需 import**(同实例)。
- **router 引用 APP 用活属性**:`from webui import app_instance` + handler 里 `app_instance.APP.xxx()`。**不要** `from webui.app_instance import APP`(import 时绑死成 None/旧实例,测试 reload(main) 换新 APP 后路由仍指旧 → 崩)。
- **monkeypatch 兼容**:mixin 里调被测试 patch 的模块级名(`get_attribute_values`/`publish_items`/`build_client`/`OssClient`/`search_attribute_values`/`_download_bytes` 等),写成 `import webui.app_service as _app_svc; _app_svc.X(...)`(`app_service.py` 顶部仍 re-export 这些名);测试 patch `app_service.X` 时活查得到。
- **新增端点**:在对应域的 router 加,或新建 `routers/<域>.py` + main `include_router`。**新增业务逻辑**:加到对应 mixin,别再塞回 App 类体。
- **helper 复用**:纯函数放 `services/_helpers.py`;`app_service.py` re-export(外部 `from webui.app_service import step_flags` 等路径兼容)。

## 演进
- mixin 是"同一 god-object 拆多文件可读化"的第一步;某域若日后需真隔离(独立测试/复用),再演进成 collaborator service(注入 store)——按域按需,非现在。
- `店铺数据分析`(analytics)落点:独立 `services/_analytics.py`(纯函数,不进 App)+ `routers/analytics.py`,见 [analytics spec](../superpowers/specs/2026-06-27-analytics-store-data-design.md)。

## 遗留(待产品决策)
- `start_image_batch/_on_image_candidate/image_batch_status/stop_image_batch`(`_ai_image.py`,Agnes 12 角度批量出图):**无端点接线、无测试、无调用方**(已被 MQ 版 `submit_batch_gen_job` 取代)。所依赖 `webui/ai_image_batch.py` 原本缺失、拆分时据调用点重建。**后续要么接端点+测试启用,要么连方法一起删**。

## 变更历史
- 2026-06-27/28 绞杀拆分(BE-T1~T10):main 980→143、app_service 3875→118;12 routers + 13 mixin;714 测试全绿、OpenAPI 89 路径契约不变、运行态 curl 各域端点正常。
