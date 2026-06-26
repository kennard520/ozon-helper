"""图集计划：据 understanding(看图理解) + 草稿图，生成槽位清单（纯函数）。"""

from __future__ import annotations


def build_image_plan(understanding: dict | None, images: list | None,
                     *, max_details: int = 2, max_points: int = 2) -> list[dict]:
    u = understanding if isinstance(understanding, dict) else {}
    imgs = [i for i in (images or []) if str(i or "").strip()]
    n = len(imgs)
    if not n:
        return []

    roles: dict[int, str] = {}
    for im in (u.get("images") or []):
        if isinstance(im, dict) and isinstance(im.get("idx"), int) and 0 <= im["idx"] < n:
            roles[im["idx"]] = str(im.get("role") or "")

    def by_role(kw: str) -> list[int]:
        return [i for i in range(n) if kw in roles.get(i, "")]

    overall = by_role("整体") or ([0] if n else [])
    details = by_role("细节") or by_role("卖点")
    sizes = by_role("尺寸")
    base = overall[0] if overall else 0
    points = [str(p).strip() for p in (u.get("points") or []) if str(p).strip()][:max_points]
    size_spec = str((u.get("specs") or {}).get("尺寸") or "").strip()

    plan: list[dict] = []
    if n:
        plan.append({"slot_id": "main", "role": "主图", "label": "白底主图",
                     "action": "white", "source_idx": base})
    used: set[int] = set()
    cnt = 0
    for idx in details:
        if cnt >= max_details:
            break
        if idx in used:
            continue
        used.add(idx)
        cnt += 1
        plan.append({"slot_id": f"detail{cnt}", "role": "细节", "label": f"细节图{cnt}",
                     "action": "localize", "source_idx": idx})
    if n:
        plan.append({"slot_id": "scene1", "role": "场景", "label": "场景图1",
                     "action": "scene", "source_idx": base})
    if size_spec:
        plan.append({"slot_id": "size", "role": "尺寸", "label": f"尺寸信息图({size_spec})",
                     "action": "infographic", "source_idx": (sizes[0] if sizes else base),
                     "bullets": [size_spec]})
    for i, pt in enumerate(points, 1):
        plan.append({"slot_id": f"point{i}", "role": "卖点", "label": f"卖点图{i}: {pt[:16]}",
                     "action": "infographic", "source_idx": base, "bullets": [pt]})
    return plan
