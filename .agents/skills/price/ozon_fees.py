"""Adapter that lets calc.py read commission and shipping from the
official Ozon XLSX-derived `ozon-fees.json`, with graceful fallback to the
hand-curated params.json values when the json is missing.

JSON producer:  tools/ozon-fees-parser  (run `python -m ozon_fees_parser extract`)
JSON consumer:  .claude/skills/price/calc.py

Why an alias table:
  params.json uses 9 coarse buckets (家居装饰 / 收纳整理 / ...). The official
  Tarifs_CN sheet has 80 fine subcategories (装饰、收纳与储物 / 装饰材料 / 节日
  装饰用品 / ...). One coarse bucket can map to multiple fine subcategories;
  we pick the most representative one as the primary, and fall back to the
  average of a group when needed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Path resolution: this file lives in .claude/skills/price/.
# ozon-fees.json lives in tools/ozon-fees-parser/data/.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[3]
_FEES_JSON = _REPO_ROOT / "tools" / "ozon-fees-parser" / "data" / "ozon-fees.json"


# Map the 9 coarse buckets used in params.json to the canonical (primary)
# Ozon official subcategory name. When the primary is missing from the
# fees JSON, we fall back to the params.json hardcoded value.
#
# Reference: Tarifs_CN_01_12_2025 sub_zh names (verified against actual data).
COARSE_TO_OZON_SUB: dict[str, str] = {
    # Verified against Tarifs_CN_01_12_2025 sub_zh column on 2026-05-18.
    "家居装饰":  "装饰、清洁与储物",
    "收纳整理":  "装饰、清洁与储物",
    "宠物配件":  "宠物用品",
    "办公文具":  "兴趣、创意与文具",
    "节日礼品":  "新年装饰用品",
    "定制类":    "装饰、清洁与储物",       # no precise match; fall back to home decor
    "美妆":      "美容与健康",
    "服装":      "服装和配饰",
    "通用":      "装饰、清洁与储物",       # default sensible bucket
}


_cache: dict[str, Any] | None = None


def load_fees(path: Path = _FEES_JSON) -> dict[str, Any] | None:
    """Load ozon-fees.json, cached. Returns None if missing/unreadable."""
    global _cache
    if _cache is not None:
        return _cache
    if not path.is_file():
        return None
    try:
        _cache = json.loads(path.read_text(encoding="utf-8"))
        return _cache
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ozon-fees] warning: {path} unreadable: {exc}", file=sys.stderr)
        return None


def _pick_price_tier(price_rub: float, tiers: list[int]) -> int:
    """Map a RUB price to its tier index (0-based) given boundary list.

    tiers = [1500, 5000] → 3 segments:
        price ≤ 1500       → 0
        1500 < price ≤ 5000 → 1
        price > 5000       → 2
    """
    for i, boundary in enumerate(tiers):
        if price_rub <= boundary:
            return i
    return len(tiers)


def lookup_commission(
    fulfillment: str,
    coarse_category: str,
    market_price_rub: float | None,
    fallback: float,
) -> tuple[float, dict[str, Any] | None]:
    """Look up Ozon commission % for (fulfillment mode, category, price tier).

    Returns (rate, source_info). source_info is None when fallback is used,
    otherwise a dict {sub_zh, price_tier, effective_from}.
    """
    fees = load_fees()
    if fees is None or not fees.get("commission"):
        return fallback, None
    comm = fees["commission"]
    sub_zh = COARSE_TO_OZON_SUB.get(coarse_category)
    if not sub_zh:
        return fallback, None
    match = next(
        (c for c in comm["categories"] if c["sub_zh"] == sub_zh),
        None,
    )
    if match is None:
        return fallback, None
    rates = match.get(fulfillment.lower())
    if not rates:
        return fallback, None

    # If price is unknown, take the middle tier (1500-5000 RUB band) as a
    # reasonable default — most green-zone categories sit there.
    if market_price_rub is None:
        tier_idx = 1
    else:
        tier_idx = _pick_price_tier(market_price_rub, comm.get("price_tiers_rub", [1500, 5000]))
    if tier_idx >= len(rates):
        tier_idx = len(rates) - 1

    return rates[tier_idx], {
        "sub_zh":           sub_zh,
        "tier_idx":         tier_idx,
        "tier_label":       _tier_label(tier_idx, comm.get("price_tiers_rub", [1500, 5000])),
        "effective_from":   comm.get("_effective_from"),
        "source_file":      comm.get("_source_filename"),
    }


def _tier_label(idx: int, tiers: list[int]) -> str:
    if idx == 0:
        return f"≤{tiers[0]} ₽"
    if idx >= len(tiers):
        return f">{tiers[-1]} ₽"
    return f"{tiers[idx - 1]}-{tiers[idx]} ₽"


# ----- Shipping lookup --------------------------------------------------

def lookup_rfbs_china_post(
    weight_g: float,
    market_price_rub: float | None,
    mode: str = "ground",
) -> dict[str, Any] | None:
    """Find best matching China Post route for an rFBS package.

    `mode`:
        "ground" → cheaper Economy/ground freight (default, slower)
        "air"    → Standard air freight (forbidden for batteries)

    Returns the route dict augmented with computed cost_cny, or None if no
    matching route (likely because weight or value exceeds China Post limits).
    """
    fees = load_fees()
    if fees is None or not fees.get("shipping_rfbs_china_post"):
        return None
    routes = fees["shipping_rfbs_china_post"]["routes"]
    # Filter Russia-bound routes matching mode and weight band
    candidates = [
        r for r in routes
        if r.get("destination") == "Russia"
        and r.get("mode") == mode
        and (r.get("weight_max_g") or 0) >= weight_g
        and (market_price_rub is None or (r.get("value_max_rub") or 0) >= market_price_rub)
    ]
    if not candidates:
        return None
    route = candidates[0]
    cost_cny = (route.get("base_cny") or 0) + (route.get("per_g_cny") or 0) * weight_g
    return {**route, "computed_cost_cny": round(cost_cny, 2)}


def lookup_fbp_china(
    weight_g: float,
    market_price_rub: float | None,
    preferred_carrier: str | None = None,
    service_level: str | None = "Standard",
) -> dict[str, Any] | None:
    """Find best matching FBP carrier for an FBP package, prefer cheapest."""
    fees = load_fees()
    if fees is None or not fees.get("shipping_fbp_china"):
        return None
    carriers = fees["shipping_fbp_china"]["carriers"]
    candidates = []
    for c in carriers:
        if c.get("destination") not in ("Russia", "俄罗斯"):
            continue
        if (c.get("weight_max_g") or 0) < weight_g:
            continue
        if (c.get("weight_min_g") or 0) > weight_g:
            continue
        if market_price_rub is not None:
            vmin = c.get("value_min_rub") or 0
            vmax = c.get("value_max_rub") or 10**9
            if not (vmin <= market_price_rub <= vmax):
                continue
        if preferred_carrier and c.get("carrier_3pl") != preferred_carrier:
            continue
        if service_level and c.get("service_level") != service_level:
            continue
        candidates.append(c)
    if not candidates:
        return None
    # Pick cheapest by base + per_g × weight
    def total(c):
        return (c.get("base_cny") or 0) + (c.get("per_g_cny") or 0) * weight_g
    candidates.sort(key=total)
    chosen = candidates[0]
    return {**chosen, "computed_cost_cny": round(total(chosen), 2)}
