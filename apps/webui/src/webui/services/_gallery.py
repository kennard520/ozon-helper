from __future__ import annotations


class GalleryMixin:
    """图集操作：图片复制、图集增删改序。"""

    def copy_images_to_draft(self, draft_id, image_urls, target_draft_ids):
        if not image_urls:
            raise ValueError("未选择图片")
        targets = [int(t) for t in (target_draft_ids or []) if int(t)]
        if not targets:
            raise ValueError("未指定目标变体")
        src = self.store.get_draft(draft_id)
        if src is None:
            raise KeyError(f"draft {draft_id} not found")
        vg_src = str((src.get("source_raw") or {}).get("variant_group") or "")
        for tid in targets:
            tgt = self.store.get_draft(tid)
            if tgt is None:
                raise KeyError(f"draft {tid} not found")
            vg_tgt = str((tgt.get("source_raw") or {}).get("variant_group") or "")
            if vg_src and vg_src != vg_tgt:
                raise ValueError("只能在同一变体组内复制图片")
        added = self.store.copy_images(draft_id, image_urls, targets)
        return {"ok": True, "added": added}

    def gallery_add(self, draft_id, image_ids):
        self.store.gallery_add(int(draft_id), [int(i) for i in (image_ids or [])])
        return self.store.get_draft(int(draft_id))

    def gallery_remove(self, draft_id, image_ids):
        self.store.gallery_remove(int(draft_id), [int(i) for i in (image_ids or [])])
        return self.store.get_draft(int(draft_id))

    def gallery_reorder(self, draft_id, image_ids):
        self.store.gallery_reorder(int(draft_id), [int(i) for i in (image_ids or [])])
        return self.store.get_draft(int(draft_id))

    def gallery_delete(self, draft_id, image_id):
        self.store.gallery_delete(int(draft_id), int(image_id))
        return self.store.get_draft(int(draft_id))
