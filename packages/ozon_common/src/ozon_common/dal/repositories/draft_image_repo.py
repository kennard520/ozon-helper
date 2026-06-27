"""DraftImageRepo — worker 出图链路对 drafts/draft_images 的 SQLAlchemy Core 访问层。

等价替换 ozon_common.draft_images.DataStore 的三个方法:
  - add_draft_image
  - get_draft  (含 _row_to_draft 拼装,字段形状完全一致)
  - load_draft_images  (附加,供 webui/worker 共用)
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, insert, select

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import draft_images as DI
from ozon_common.dal.schema import drafts as DR
from ozon_common.jsonio import loads_json, utc_now_iso


class DraftImageRepo(BaseRepo):
    # ------------------------------------------------------------------
    # draft_images 读写
    # ------------------------------------------------------------------

    def load_draft_images(self, draft_id: int) -> list[dict[str, Any]]:
        """按 position 升序返回 draft 的图片列表,每条含 url/type/source。"""
        rows = self.s.execute(
            select(DI.c.url, DI.c.type, DI.c.source)
            .where(DI.c.draft_id == int(draft_id))
            .order_by(DI.c.position)
        ).all()
        return [{"url": r.url, "type": r.type, "source": r.source} for r in rows]

    def add_draft_image(
        self,
        draft_id: int,
        url: str,
        *,
        type: str = "",
        source: str = "generated",
        in_gallery: int | None = None,
    ) -> int:
        """插入一条 draft_image 记录,position 自动取当前最大值 +1,返回新行 id。

        与 DataStore.add_draft_image 行为一致:
          - position = MAX(position)+1(空时从 0 开始)
          - created_at 用 utc_now_iso()
          - in_gallery:默认按 source 推断(generated→1,其它→0)
        """
        if in_gallery is None:
            in_gallery = 1 if source == "generated" else 0
        nxt = (
            self.s.execute(
                select(func.coalesce(func.max(DI.c.position), -1) + 1).where(
                    DI.c.draft_id == int(draft_id)
                )
            ).scalar()
            or 0
        )
        res = self.s.execute(
            insert(DI).values(
                draft_id=int(draft_id),
                position=int(nxt),
                url=str(url),
                type=str(type or ""),
                source=str(source),
                in_gallery=int(in_gallery),
                created_at=utc_now_iso(),
            )
        )
        return int(res.inserted_primary_key[0])

    # ------------------------------------------------------------------
    # drafts 读(含拼装 draft_images)
    # ------------------------------------------------------------------

    def get_draft(self, draft_id: int) -> dict[str, Any] | None:
        """读取 drafts 行并拼装 images/source_raw,字段形状与 DataStore.get_draft 完全一致。"""
        row = self.s.execute(
            select(DR).where(DR.c.id == int(draft_id))
        ).first()
        if row is None:
            return None
        return self._row_to_draft(row)

    def _row_to_draft(self, row) -> dict[str, Any]:
        """将 drafts 行 + draft_images 查询结果拼成与 DataStore._row_to_draft 等价的 dict。

        字段对照(DataStore 原注释):
          images      = [url, ...]               按 position 排序
          source_raw  = {..., image_types: {url: type}}  仅有 type 的条目才进 image_types
          images_json = loads_json(images_json_col, [])
          type_id     = "" 若列不存在(SQLite 旧库兼容)
        """
        m = row._mapping

        # 查 draft_images,只取图集(in_gallery=1),与 webui DraftRepo 保持一致
        dimg_rows = self.s.execute(
            select(DI.c.url, DI.c.type)
            .where(DI.c.draft_id == int(m["id"]), DI.c.in_gallery == 1)
            .order_by(DI.c.position)
        ).all()

        images = [r.url for r in dimg_rows]
        image_types = {r.url: r.type for r in dimg_rows if r.type}

        # source_raw:先还原 JSON 列,再注入 image_types(与 DataStore 逻辑相同)
        source_raw = loads_json(m.get("source_raw_json"), {}) or {}
        if image_types:
            source_raw["image_types"] = image_types
        elif "image_types" not in source_raw:
            source_raw["image_types"] = {}

        return {
            "id": m["id"],
            "source_platform": m["source_platform"],
            "source_url": m["source_url"],
            "source_title": m["source_title"],
            "ozon_title": m["ozon_title"],
            "description": m["description"],
            "category_id": m["category_id"],
            # type_id 兼容旧库(列可能不存在时给 "")
            "type_id": m.get("type_id", "") or "",
            "images": images,
            "source_raw": source_raw,
            "images_json": loads_json(m.get("images_json"), []),
        }
