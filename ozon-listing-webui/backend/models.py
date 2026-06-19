from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AuthIn(BaseModel):
    username: str
    password: str


class SettingsIn(BaseModel):
    ozon_client_id: str | None = None
    ozon_api_key: str | None = None
    rub_cny: float | str | None = None
    contract_currency: str | None = None
    translate_engine: str | None = None
    translate_api_base: str | None = None
    translate_api_key: str | None = None
    translate_model: str | None = None
    ai_auto_apply: bool | None = None
    ai_chat_provider: str | None = None
    ai_card_vision: bool | None = None
    agnes_api_base: str | None = None
    agnes_api_key: str | None = None
    agnes_chat_model: str | None = None
    agnes_image_model: str | None = None
    agnes_video_model: str | None = None
    ozon_stores: list | None = None
    last_publish_store: str | None = None
    translate_mode: str | None = None
    ai_text: dict | None = None
    ai_image: dict | None = None
    ai_video: dict | None = None
    oss_endpoint: str | None = None
    oss_bucket: str | None = None
    oss_access_key_id: str | None = None
    oss_access_key_secret: str | None = None
    oss_public_base: str | None = None


class CollectIn(BaseModel):
    urls: str = ""
    source_platform: str = "1688"


class CollectKeywordIn(BaseModel):
    keyword: str = ""
    limit: int = 20
    price_min: float | None = None
    price_max: float | None = None


class ImagePromptsIn(BaseModel):
    n_points: int = 3


class AiImageIn(BaseModel):
    # Agnes 生图：text2img(营销图) / img2img(白底主图等)
    mode: str = "text2img"
    prompt: str = ""
    source_url: str | None = None
    size: str | None = None
    as_main: bool | None = None


class AiVideoIn(BaseModel):
    # Agnes 图生视频：默认主图 + 默认运镜提示词
    prompt: str | None = None
    image_url: str | None = None


class DraftPatchIn(BaseModel):
    # 草稿字段开放透传（与现有 PATCH 行为一致），用 dict 接住任意子集
    model_config = {"extra": "allow"}


class BatchUpdateDraftsIn(BaseModel):
    # 批量给多个草稿打补丁（批量设库存/仓库）；后端只放行 stock/warehouse_id
    ids: list[int]
    stock: int | None = None
    warehouse_id: int | None = None


class CommissionMapIn(BaseModel):
    cat: int
    type: int
    parent_en: str = ""
    sub_en: str = ""
    rfbs: list[Any] = []


class OzonPullIn(BaseModel):
    visibility: str = "ALL"


class DefaultWarehouseIn(BaseModel):
    warehouse_id: int


class FbsPullIn(BaseModel):
    status: str = "awaiting_packaging"
    days: int = 14


class ProcStateIn(BaseModel):
    purchase_state: str
    note: str = ""


class ShipIn(BaseModel):
    posting_number: str


class AiProposalPatchIn(BaseModel):
    op: str
    key: str | None = None
    id: int | None = None
    value: Any | None = None


class PublishIn(BaseModel):
    store_client_id: str | None = None


class BatchCollectIn(BaseModel):
    start: int
    end: int


class AiImageBatchIn(BaseModel):
    source_url: str | None = None


class ImageCandidatesApplyIn(BaseModel):
    indices: list[int]


class ExtCollectIn(BaseModel):
    url: str
    # 插件就地取价(已换成人民币)随采集一起传来；缺省=不覆盖(沿用采集器结果)
    price: float | None = None
    old_price: float | None = None
    rating: float | None = None
    feedbacks: int | None = None


class ExtCollectParsedIn(BaseModel):
    url: str
    data: dict | None = None


class ExtSnapshotIn(BaseModel):
    product_id: str
    sku: str | None = None
    follow_count: int | None = None
    price_min: float | None = None
    price_max: float | None = None
    sellers: list[dict] | None = None


class PublishGroupIn(BaseModel):
    variant_group: str
    store_client_id: str | None = None
    model_name: str | None = None


class AdminCreateUserIn(BaseModel):
    username: str
    password: str
    max_stores: int = 1


class AdminUpdateUserIn(BaseModel):
    max_stores: int | None = None
    status: str | None = None   # active / disabled
    password: str | None = None
