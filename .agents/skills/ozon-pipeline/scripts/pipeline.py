#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ozon 选品→上架全流程 pipeline（单文件，本地跑）
链路: Ozon自动逛 → BCS(月销/跟卖/转化) → 1688国际站进价 → 算利润 → 筛选
      → 素材(下载竞品主图, 标记待处理) → 上架载荷
      → [agent 接力] 处理素材：豆包 AI 原创生成
        (image_edit 抠图去背景留产品本体 → image_edit/image_gen 原创白底/场景/信息图)
      → OSS 直链替换载荷 images → /v3/product/import 原创建卡

⚠️ 重要规则：
  - 禁止使用 /v1/product/import-by-sku（复制上架通道）
  - 上架一律走 /v3/product/import 原创建卡
  - 定价规则：建议销售价 → 划线价×4 / 非促销价×1.9 / 促销活动限制=建议价 / 成本=建议价
  - 竞品图仅作参考：最终上架图必须由豆包 AI 原创生成（image_edit / image_gen，
    不以竞品画面为锚点；抠图去背景只留产品本体）后，以 OSS 直链替换载荷 images。

用法:
    python pipeline.py "мультиметр" [--pages 2] [--min-sales 50] [--min-profit 20]
    python pipeline.py --resume picks_output/pipeline_xxx.json   # 复用上次抓取结果继续

依赖: 项目 .venv（cloakbrowser），BCS token 见 scripts/config.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]          # ozon-helper（scripts→ozon-pipeline→skills→.agents→仓库根）
SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
OUT_DIR = ROOT / "picks_output"
PROFILE = OUT_DIR / ".ozon_tmp_profile"
CALC_PROFIT = SKILL_DIR.parent / "ozon-profit-calculator" / "scripts" / "calc_profit.py"
CONFIG = SCRIPTS_DIR / "config.json"

# ---------- 默认配置（可被 config.json 覆盖） ----------
DEFAULTS = {
    "BCS_BASE": "https://ozon.bcserp.com/prod-api",
    "BCS_TOKEN": "",            # 从 config.json 或环境变量读
    "BCS_LIMIT_KEY": "",        # 从 config.json 或环境变量读
    "RUB_TO_RMB": 0.093,
    "MIN_SALES": 50,            # 最低月销
    "MIN_PROFIT_RMB": 20,       # 最低单件利润(¥)
    "MAX_PRICE_RUB": 8000,      # 售价上限
    "PAGES": 2,                 # 每关键词抓几页
    "COMMISSION_DEFAULT": 0.17, # 无 BCS 佣金表时兜底
    "CATEGORY": "other",        # 传给 calc_profit: car|other
}


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        try:
            cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[!] config.json 解析失败: {e}，用默认配置")
    # 环境变量优先
    cfg["BCS_TOKEN"] = os.environ.get("BCS_TOKEN", cfg["BCS_TOKEN"])
    cfg["BCS_LIMIT_KEY"] = os.environ.get("BCS_LIMIT_KEY", cfg["BCS_LIMIT_KEY"])
    return cfg


# ============ 阶段1: Ozon 自动逛（cloakbrowser 搜索页收集 SKU） ============

class SkuExtractor(HTMLParser):
    """从 Ozon 搜索页 HTML 提取商品链接里的 SKU + 标题锚文本。"""

    def __init__(self):
        super().__init__()
        self.skus = []          # [(sku, anchor_text)]
        self._seen = set()
        self._cur_sku = None    # 当前 <a> 的 sku（None 表示非商品链接）
        self._cur_text = []     # 当前 <a> 的文本片段（可能是多个节点，如促销徽标）

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            href = d.get("href", "")
            m = re.search(r"/product/[^/]+-(\d{7,})/?", href)
            self._cur_sku = m.group(1) if m else None
            self._cur_text = []

    def handle_data(self, data):
        if self._cur_sku is not None:
            t = data.strip()
            if t:
                self._cur_text.append(t)

    def handle_endtag(self, tag):
        if tag == "a":
            sku = self._cur_sku
            self._cur_sku = None
            text = self._cur_text
            self._cur_text = []
            if sku and sku not in self._seen:
                self._seen.add(sku)
                title = re.sub(r"\s+", " ", " ".join(text))[:80] if text else ""
                self.skus.append((sku, title))


def browse_ozon(keywords: list[str], pages: int, cfg: dict) -> list[dict]:
    """用登录态浏览器翻搜索页，收集 SKU 列表。"""
    from cloakbrowser import launch_persistent_context

    PROFILE.mkdir(parents=True, exist_ok=True)
    print(f"[1/7] Ozon 自动逛：{keywords}（{pages}页/词，profile: {PROFILE.name}）")
    ctx = launch_persistent_context(
        user_data_dir=str(PROFILE), headless=True,
        locale="ru-RU", timezone="Europe/Moscow",
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    found: dict[str, dict] = {}
    try:
        for kw in keywords:
            for p in range(1, pages + 1):
                url = f"https://www.ozon.ru/search/?text={urllib.parse.quote(kw)}&page={p}&from_global=true"
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    time.sleep(5)
                    for i in range(4):
                        page.evaluate(f"window.scrollBy(0, {600 * (i + 1)})")
                        time.sleep(0.8)
                    html = page.content()
                    parser = SkuExtractor()
                    parser.feed(html)
                    new = 0
                    for sku, title in parser.skus:
                        if sku not in found:
                            found[sku] = {"sku": sku, "title": title, "source_kw": kw, "source_page": p}
                            new += 1
                    print(f"   第{p}页 {kw}: 新发现 {new} 个 SKU（累计 {len(found)}）")
                except Exception as e:
                    print(f"   第{p}页失败: {e}")
                time.sleep(1.5)
    finally:
        ctx.close()
    return list(found.values())


# ============ 阶段2: BCS 查数 ============

def bcs_headers(cfg):
    return {
        "Authorization": f"Bearer {cfg['BCS_TOKEN']}",
        "X-Limit-Key": cfg["BCS_LIMIT_KEY"],
        "Origin": "https://www.ozon.ru",
        "Referer": "https://www.ozon.ru/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }


def bcs_fetch(sku: str, cfg: dict) -> dict | None:
    url = f"{cfg['BCS_BASE']}/system/sku/skuss/new?sku={sku}&pageUrl=https://www.ozon.ru/product/{sku}/"
    req = urllib.request.Request(url, headers=bcs_headers(cfg))
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("code") == 200 and data.get("data"):
            return data["data"]
    except Exception as e:
        print(f"   [BCS] sku={sku} 失败: {e}")
    return None


def enrich_bcs(items: list[dict], cfg: dict) -> list[dict]:
    """对每个 SKU 查 BCS，合并月销/月GMV/跟卖/转化/佣金表等。"""
    print(f"[2/7] 查 BCS 数据（{len(items)} 个 SKU）...")
    if not cfg["BCS_TOKEN"]:
        print("   [!] 未配置 BCS_TOKEN，跳过 BCS 数据（可后续 --resume 补）")
        return items
    for i, it in enumerate(items):
        d = bcs_fetch(it["sku"], cfg)
        if not d:
            it["bcs"] = None
            continue
        it["bcs"] = d
        it["monthsales"] = d.get("monthsales", 0) or 0
        it["monthgmv"] = d.get("monthgmv", 0) or 0
        it["avgprice_rub"] = d.get("avgprice", 0) or 0
        it["dynamics"] = d.get("salesDynamics", "")
        it["views"] = d.get("views", 0) or 0
        it["sessioncount"] = d.get("sessioncount", 0) or 0
        it["goodsClickRate"] = d.get("goodsClickRate", 0) or 0
        it["convToCartPdp"] = str(d.get("convToCartPdp", "0")).replace("%", "") or "0"
        it["commission"] = d.get("commission", {}) or {}
        it["skuimg"] = d.get("skuimg", "")
        it["brand"] = d.get("brand", "")
        it["catname"] = d.get("catname", "")
        it["stock"] = d.get("stock", "")
        print(f"   [{i+1}/{len(items)}] {it['sku']} 月销{it['monthsales']} 月GMV{it['monthgmv']} "
              f"均价{it['avgprice_rub']:.0f}₽ 转化{it['convToCartPdp']}% {it['title'][:25]}")
        time.sleep(0.25)
    return items


# ============ 阶段3: 1688 国际站进价 ============

def price_from_alibaba(title: str, cfg: dict) -> dict | None:
    """1688 国际站(alibaba.com)搜同款，拿采购价区间。失败返回 None（不阻塞）。"""
    q = urllib.parse.quote(title[:40].replace(" ", " "))
    url = f"https://www.alibaba.com/trade/search?SearchText={q}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "ignore")
        prices = [float(x) for x in re.findall(r"US\s*\$?([\d.]+)", html)[:20]]
        if not prices:
            return None
        prices.sort()
        return {"min": prices[0], "p50": prices[len(prices) // 2], "max": prices[-1], "src": "alibaba"}
    except Exception as e:
        print(f"   [1688] 查询失败: {e}")
        return None


def enrich_prices(items: list[dict], cfg: dict) -> list[dict]:
    print(f"[3/7] 查 1688 国际站进价（{len(items)} 个，失败不阻塞）...")
    for i, it in enumerate(items):
        it["cn_price"] = price_from_alibaba(it["title"], cfg)
        if it["cn_price"]:
            print(f"   [{i+1}] {it['sku']} 进价 US${it['cn_price']['min']}~{it['cn_price']['max']} "
                  f"(≈¥{it['cn_price']['min']*7.2:.0f}~{it['cn_price']['max']*7.2:.0f})")
        time.sleep(0.5)
    return items


# ============ 阶段4: 算利润（调 calc_profit.py） ============

def commission_rate_for(rub_price: float, comm: dict) -> float:
    """按 BCS 佣金表(三档)取 RFBS 佣金率(小数)。"""
    if not comm:
        return 0.17
    if rub_price <= 1500:
        return float(comm.get("rfbs1500", 17)) / 100
    if rub_price <= 5000:
        return float(comm.get("rfbs1500To5000", 17)) / 100
    return float(comm.get("rfbsGreater5000", 17)) / 100


def calc_profits(items: list[dict], cfg: dict) -> list[dict]:
    """按 BCS 佣金率分组，调 calc_profit.py 算四渠道利润（口径与 calc_profit 一致）。"""
    print(f"[4/7] 算利润（调 ozon-profit-calculator，按佣金率分组）...")
    RATE_CNY_TO_RUB = 12.7154  # calc_profit.py 当天汇率口径（1CNY=?RUB）

    groups: dict[float, list[dict]] = {}
    for it in items:
        rub = it.get("avgprice_rub", 0) or 0
        if rub <= 0:
            continue
        comm_rate = commission_rate_for(rub, it.get("commission", {}))
        groups.setdefault(comm_rate, []).append((it, rub))

    for comm_rate, lst in groups.items():
        goods = []
        for it, rub in lst:
            cost = 0
            cn = it.get("cn_price")
            if cn:
                cost = round(cn["p50"] * 7.2, 2)  # USD→CNY 粗算
            goods.append({
                "name": it["sku"],
                "price": round(rub / RATE_CNY_TO_RUB, 2),  # RUB→CNY 售价（calc_profit 口径）
                "cost": cost,
                "weight": it.get("weight_g", 300),          # 无重量默认 300g（可手动改）
            })
        if not goods:
            continue
        goods_file = OUT_DIR / f"pipeline_goods_{int(comm_rate*1000)}.json"
        goods_file.write_text(json.dumps(goods, ensure_ascii=False), encoding="utf-8")
        cmd = [sys.executable, str(CALC_PROFIT), "--file", str(goods_file),
               "--category", cfg["CATEGORY"], "--commission", str(comm_rate), "--json"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            out = json.loads(res.stdout) if res.stdout.strip() else []
        except Exception as e:
            print(f"   calc_profit 调用失败(佣金{comm_rate}): {e}")
            print((res.stderr[:400] if 'res' in dir() and res.stderr else ''))
            continue
        by_name = {r.get("name"): r for r in out}
        for it, rub in lst:
            p = by_name.get(it["sku"])
            if p:
                it["profit"] = p
                it["best_channel"] = p.get("best_channel", "")
                it["profit_rmb"] = p.get("best_profit", 0)
                it["profit_margin"] = p.get("best_margin", 0)
    return items


# ============ 阶段5: 筛选 ============

def filter_items(items: list[dict], cfg: dict) -> list[dict]:
    print(f"[5/7] 筛选（月销≥{cfg['MIN_SALES']} 且 利润≥¥{cfg['MIN_PROFIT_RMB']} 且 售价≤₽{cfg['MAX_PRICE_RUB']}）...")
    good = []
    for it in items:
        if not it.get("bcs"):
            continue
        if it.get("monthsales", 0) < cfg["MIN_SALES"]:
            continue
        if it.get("avgprice_rub", 0) > cfg["MAX_PRICE_RUB"]:
            continue
        profit_rmb = it.get("profit_rmb", 0)
        if profit_rmb < cfg["MIN_PROFIT_RMB"]:
            continue
        good.append(it)
    good.sort(key=lambda x: (x.get("monthsales", 0), x.get("profit_rmb", 0)), reverse=True)
    print(f"   通过 {len(good)} 个：")
    for it in good[:15]:
        print(f"   ⭐ {it['sku']} 月销{it['monthsales']} ₽{it['avgprice_rub']:.0f} "
              f"利润¥{it.get('profit_rmb', 0):.1f} {it['title'][:35]}")
    return good


# ============ 阶段6: 素材（下载竞品主图，标记待豆包 AI 处理） ============

def download_assets(items: list[dict], cfg: dict) -> list[dict]:
    print(f"[6/7] 拉取素材到 {OUT_DIR.name}/assets ...")
    asset_dir = OUT_DIR / "assets"
    asset_dir.mkdir(exist_ok=True)
    for it in items:
        img = it.get("skuimg", "")
        if not img:
            continue
        try:
            req = urllib.request.Request(img, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            ext = ".jpg"
            p = asset_dir / f"{it['sku']}{ext}"
            p.write_bytes(data)
            it["asset_local"] = str(p)
            it["image_status"] = "pending_doubao"   # 素材已就绪，待 agent 用豆包 AI 原创生成
            it["needs_ai_generation"] = True
        except Exception as e:
            print(f"   {it['sku']} 图片下载失败: {e}")
    n = len([x for x in items if x.get("asset_local")])
    print(f"   完成，{n} 张图")
    print("   处理素材：由 agent 接力，用豆包 AI 原创生成"
          "（image_edit 抠图去背景留产品本体 → image_edit/image_gen 原创白底/场景/信息图）")
    return items


# ============ 阶段7: 上架载荷（Ozon Seller API 凭证可选） ============

def build_listing_payload(items: list[dict], cfg: dict) -> dict:
    """生成待上架载荷（无凭证时输出 JSON，有凭证时可接 v3/product/import）。

    定价规则（用户约定）：
      - 建议销售价 = 竞品均价换算成人民币
      - 非促销最高价格（price）= 建议销售价 × 1.9
      - 划线价格（old_price）= 建议销售价 × 4
      - 促销活动限制价格（marketing_price）= 建议销售价
      - 成本（cost）= 建议销售价

    图片字段说明：
      - images 里的是竞品图 URL，仅作占位参考，禁止直接上架；
      - image_status=pending_doubao 表示待 agent 用豆包 AI（image_edit/image_gen）
        原创生成合规套图后，以 OSS 公网直链整体替换本字段。
    """
    print("[7/7] 生成上架载荷 ...")
    RATE_CNY_TO_RUB = 12.7154  # 与 calc_profit.py 口径一致
    payload = {"items": []}
    for it in items:
        rub_price = it.get("avgprice_rub", 0)
        suggested_price = round(rub_price / RATE_CNY_TO_RUB, 0)  # 人民币建议售价

        # 按定价规则计算 Ozon 后台4个价格字段
        oz_price = round(suggested_price * 1.9, 0)        # 非促销最高价格
        oz_old_price = round(suggested_price * 4, 0)      # 划线价格
        oz_marketing_price = round(suggested_price, 0)    # 促销活动限制价格
        oz_cost = round(suggested_price, 0)               # 成本

        payload["items"].append({
            "sku_ozon": it["sku"],
            "title": it.get("title", ""),
            "price_rub": rub_price,
            "price_cny": suggested_price,
            # Ozon 后台4个价格字段
            "price": str(oz_price),               # 非促销最高价格
            "old_price": str(oz_old_price),       # 划线价格
            "marketing_price": str(oz_marketing_price),  # 促销活动限制价格
            "cost": str(oz_cost),                  # 成本
            "images": [it.get("skuimg", "")],     # 竞品图仅占位参考，上架前由豆包 AI 生成后整体替换
            "image_status": it.get("image_status", "pending_doubao"),
            "needs_ai_generation": it.get("needs_ai_generation", True),
            "profit_rmb": it.get("profit_rmb", 0),
            "commission": it.get("commission", {}),
            "source": {"bcs": it.get("bcs", {}).get("skuid")},
        })
    return payload


def main():
    ap = argparse.ArgumentParser(description="Ozon 选品→上架全流程")
    ap.add_argument("keywords", nargs="*", help="俄语搜索词（可多个）")
    ap.add_argument("--pages", type=int, default=None, help="每词抓几页")
    ap.add_argument("--min-sales", type=int, default=None)
    ap.add_argument("--min-profit", type=float, default=None)
    ap.add_argument("--max-price", type=int, default=None)
    ap.add_argument("--resume", type=str, help="从上次保存的 JSON 继续（跳过逛）")
    ap.add_argument("--skip-bcs", action="store_true", help="跳过 BCS 查询")
    ap.add_argument("--skip-price", action="store_true", help="跳过 1688 查价")
    ap.add_argument("--no-browser", action="store_true", help="只跑 BCS+利润（需要 --skus 或 --resume）")
    ap.add_argument("--skus", type=str, help="逗号分隔的 SKU 列表，跳过浏览")
    args = ap.parse_args()

    cfg = load_config()
    if args.pages: cfg["PAGES"] = args.pages
    if args.min_sales: cfg["MIN_SALES"] = args.min_sales
    if args.min_profit: cfg["MIN_PROFIT_RMB"] = args.min_profit
    if args.max_price: cfg["MAX_PRICE_RUB"] = args.max_price
    OUT_DIR.mkdir(exist_ok=True)

    # 恢复或浏览
    items: list[dict] = []
    if args.resume and Path(args.resume).exists():
        items = json.loads(Path(args.resume).read_text(encoding="utf-8"))
        print(f"[1/7] 复用上次结果 {len(items)} 个（跳过浏览）")
    elif args.skus:
        items = [{"sku": s.strip(), "title": "", "source": "manual"} for s in args.skus.split(",") if s.strip()]
        print(f"[1/7] 手动指定 {len(items)} 个 SKU（跳过浏览）")
    elif args.no_browser:
        print("[1/7] --no-browser 但未提供 SKU/--resume，无可处理对象")
        return
    else:
        if not args.keywords:
            print("需要关键词：python pipeline.py \"мультиметр\"")
            return
        items = browse_ozon(args.keywords, cfg["PAGES"], cfg)

    if not items:
        print("没有收集到商品，退出")
        return

    if not args.skip_bcs:
        items = enrich_bcs(items, cfg)
    if not args.skip_price:
        items = enrich_prices(items, cfg)
    items = calc_profits(items, cfg)
    good = filter_items(items, cfg)
    good = download_assets(good, cfg)
    payload = build_listing_payload(good, cfg)

    # 保存
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_file = OUT_DIR / f"pipeline_{ts}.json"
    out_file.write_text(json.dumps({"all": items, "picks": good, "listing_payload": payload},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 全流程完成")
    print(f"   候选 {len(good)} 个 | 完整数据 -> {out_file}")
    print(f"   素材已下载（assets/），处理素材由 agent 用豆包 AI（image_edit/image_gen）接力，产物落盘 {OUT_DIR.name}/assets_processed")
    print(f"   上架载荷 -> 见文件内 listing_payload（images 为占位，需豆包 AI 生成合规图后以 OSS 直链替换）")
    if not cfg["BCS_TOKEN"]:
        print("   ⚠️ 本次未配置 BCS_TOKEN，数据不完整。把 token 填进 scripts/config.json 后重跑。")


if __name__ == "__main__":
    main()
