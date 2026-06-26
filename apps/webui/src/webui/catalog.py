"""Ozon 类目树 → 拍平成可搜索的叶子(description_category_id + type_id + 路径)。

类目树很大，拉一次缓存在内存。search() 按关键词(中/俄文)在路径里子串匹配。
"""
from __future__ import annotations

from typing import Any, Iterator

# 中文电商习惯叫法 → Ozon ZH_HANS 译名里实际用的词。
# Ozon 的中文类目树是机翻直译，性别/俗称都不拆，习惯叫法常常 0 命中。
# 这里把习惯词扩展成"或匹配"的候选，命中任一即算命中。
SYNONYMS: dict[str, list[str]] = {
    "女装": ["连衣裙", "裙", "上衣", "T恤", "卫衣", "外套", "服装"],
    "男装": ["衬衫", "T恤", "卫衣", "外套", "裤", "服装"],
    "童装": ["婴儿服装", "儿童", "服装"],
    "裙子": ["连衣裙", "裙"],
    "鞋": ["鞋", "靴", "凉鞋", "运动鞋"],
    "包": ["包", "背包", "手提包", "钱包"],
    "首饰": ["首饰", "项链", "耳环", "手镯", "戒指"],
    "家居": ["家居", "家具", "住宅和花园"],
    "宠物": ["宠物", "猫", "狗"],
    "玩具": ["玩具", "游戏"],
    "厨房": ["厨房", "餐具", "厨具"],
    "收纳": ["收纳", "储物", "整理"],
    "饰品": ["首饰", "配饰", "装饰"],
    "文具": ["文具", "办公", "书写"],
}


def _to_select_nodes(nodes: list[dict], parent_cat_id: int | None) -> list[dict]:
    """把 Ozon 原始嵌套树转成 el-tree-select 节点：
    - type 节点(末级)：可选叶子 value=`cat-type`，disabled 的过滤掉
    - 类目节点(中间)：disabled=True(仅展开不可选)，递归 children；cat_id 向子透传
    """
    out: list[dict] = []
    for n in nodes or []:
        if n.get("type_id"):
            if n.get("disabled"):
                continue
            cid = n.get("description_category_id") or parent_cat_id
            out.append({
                "value": f"{cid}-{n['type_id']}",
                "label": n.get("type_name") or "",
            })
        else:
            cid = n.get("description_category_id", parent_cat_id)
            children = _to_select_nodes(n.get("children") or [], cid)
            out.append({
                "value": f"cat-{cid}",
                "label": n.get("category_name") or "",
                "disabled": True,
                "children": children,
            })
    return out


def _flatten(nodes: list[dict], ancestors: list[str], desc_cat_id: int | None) -> Iterator[dict]:
    for n in nodes or []:
        if n.get("type_id"):
            yield {
                "description_category_id": desc_cat_id,
                "type_id": n["type_id"],
                "type_name": n.get("type_name") or "",
                "path": " / ".join([*ancestors, n.get("type_name") or ""]),
                "disabled": bool(n.get("disabled")),
            }
        else:
            cid = n.get("description_category_id", desc_cat_id)
            name = n.get("category_name") or ""
            yield from _flatten(n.get("children") or [], [*ancestors, name], cid)


class Catalog:
    # 本地优先：先用 store 里缓存的 leaves；没有再拉 Ozon 并持久化。
    def __init__(self, store: Any = None, language: str = "ZH_HANS") -> None:
        self._leaves: list[dict] | None = None
        self._raw_tree: list | None = None
        self._language = language
        self._store = store

    def find_leaf(self, client: Any, cat_id: int, type_id: int) -> dict | None:
        """按 (description_category_id, type_id) 反查叶子，给前端回显可读类目名用。"""
        self.load(client)
        for leaf in self._leaves or []:
            if leaf.get("description_category_id") == cat_id and leaf.get("type_id") == type_id:
                return leaf
        return None

    def has_cache(self) -> bool:
        # 本地是否已有可用类目缓存（内存或 SQLite）——有就能纯离线搜索
        if self._leaves is not None:
            return True
        return bool(self._store and self._store.load_catalog_leaves(self._language))

    def load(self, client: Any, *, force: bool = False) -> int:
        if self._leaves is not None and not force:
            return len(self._leaves)
        if self._store and not force:
            cached = self._store.load_catalog_leaves(self._language)
            if cached:
                self._leaves = cached
                return len(self._leaves)
        if client is None:
            raise RuntimeError("类目缓存为空，且未配置 Ozon API，无法首次拉取类目树")
        tree = client.get_category_tree(language=self._language)
        root = tree.get("result") or tree
        leaves = [x for x in _flatten(root, [], None) if not x["disabled"]]
        self._leaves = leaves
        self._raw_tree = root
        if self._store:
            self._store.save_catalog_leaves(self._language, leaves)
            self._store.save_catalog_tree(self._language, root)
        return len(self._leaves)

    def has_tree_cache(self) -> bool:
        if self._raw_tree is not None:
            return True
        return bool(self._store and self._store.load_catalog_tree(self._language))

    def tree(self, client: Any) -> list[dict]:
        """返回 el-tree-select 嵌套树。本地缓存优先，无缓存才用 client 拉取。"""
        if self._raw_tree is None:
            if self._store:
                cached = self._store.load_catalog_tree(self._language)
                if cached is not None:
                    self._raw_tree = cached
            if self._raw_tree is None:
                if client is None:
                    raise RuntimeError("类目树缓存为空，且未配置 Ozon API，无法首次拉取")
                # force=True：老用户已有叶子缓存时 load() 会短路不拉树，
                # 强制拉取确保 _raw_tree 被填（否则返回空树 → 前端下拉为空）。
                self.load(client, force=True)
        return _to_select_nodes(self._raw_tree or [], None)

    def raw_tree(self, client: Any) -> list:
        """返回 Ozon 原始嵌套树根列表（给 AI 逐层下钻用）。本地缓存优先。"""
        if self._raw_tree is None:
            if self._store:
                cached = self._store.load_catalog_tree(self._language)
                if cached is not None:
                    self._raw_tree = cached
            if self._raw_tree is None:
                if client is None:
                    raise RuntimeError("类目树缓存为空，且未配置 Ozon API，无法首次拉取")
                self.load(client, force=True)
        return self._raw_tree or []

    def search(self, client: Any, query: str, *, limit: int = 30) -> list[dict]:
        self.load(client)
        q = (query or "").strip().lower()
        if not q:
            # 空查询 = 浏览全部（按路径排序，截断到 limit 防前端卡顿）
            return sorted(self._leaves or [], key=lambda x: x["path"])[:limit]
        terms = q.split()

        def _match_one(term: str, hay: str) -> bool:
            # 俄语词形容错：去掉词尾 1-2 个字母再匹配（сумка↔сумки、дорожная↔дорожные）
            if term in hay:
                return True
            if len(term) >= 5 and term[:-1] in hay:
                return True
            if len(term) >= 7 and term[:-2] in hay:
                return True
            return False

        def _match_rank(term: str, hay: str) -> int | None:
            # 习惯叫法扩展：原词命中=0(最相关)，命中第 i 个同义词=i+1，都不中=None
            if _match_one(term, hay):
                return 0
            for i, alt in enumerate(SYNONYMS.get(term, ())):
                if _match_one(alt.lower(), hay):
                    return i + 1
            return None

        hits = []
        for leaf in self._leaves or []:
            hay = leaf["path"].lower()
            ranks = [_match_rank(t, hay) for t in terms]
            if all(r is not None for r in ranks):
                hits.append((sum(ranks), leaf))  # type: ignore[arg-type]
        # 同义词命中越靠前(rank 小)越相关 → 类型名直接命中 → 路径短(叶子更具体)
        # 用逐词判断，避免多词查询(含空格)时整串永远 not in 导致该项权重失效
        def _name_hit(leaf: dict) -> bool:
            name = leaf["type_name"].lower()
            return any(t in name for t in terms)

        hits.sort(key=lambda kv: (kv[0], not _name_hit(kv[1]), len(kv[1]["path"])))
        return [leaf for _, leaf in hits[:limit]]
