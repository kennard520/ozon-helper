#!/usr/bin/env python3
"""跨境一件代发盈亏测算器 v3（2026-05 参数版）。

v3 改动：
- 所有可变参数外置到 params.json（佣金/运费/汇率/类目/平台/默认值）
- 汇率实时获取（open.er-api.com），失败回退 params.json 缓存
- 佣金改为 平台×类目 二维表
- 运费改为阶梯函数（首重/续重）
- 新增成本因子：国内运费、包装费、活动折扣、达人佣金、旺季附加、进口税
- 支持体积重（L×W×H）
- 竞品售价对比（market_price）
- 未指定类目时输出全类目矩阵
- 每单利润绝对值
- Temu Y2 供货价模式标注

公式（v3）：
    实际运费 ship_eff = ship(billable_weight) × (1 + seasonal_surcharge)
    固定成本 = cost + domestic_ship + packing_fee + ship_eff + import_tax
    损失率 L = return_rate + malicious_return + factory_loss + warehouse_error
    有效退货处理 = (return_rate + malicious_return + warehouse_error) × return_handling
    收入系数 S = (1 - promo_discount) × (1 - commission - payment_fee - ad_pct - fx_buffer - affiliate_pct)

    E[profit] = (1 - L) × P × S - 固定成本 - 有效退货处理
    P_min = (固定成本 + 有效退货处理) / [(1 - L) × S]
    P_target = P_min / (1 - margin_target)

CLI:
    python calc.py --cost 20 --weight 500
    python calc.py --cost 20 --weight 500 --category 家居装饰
    python calc.py --cost 20 --weight 500 --platform ozon --category 宠物配件
    python calc.py --cost 8 --weight 100 --length 20 --width 15 --height 10
    python calc.py --cost 15 --weight 200 --market-price 60
    python calc.py --cost 20 --weight 500 --price 80 --ad-pct 0.08
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import dataclass, asdict, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

CONFIG_PATH = Path(__file__).parent / "params.json"
ALL_PLATFORMS = ["ali", "temu_y2", "tt_sea", "ozon"]


def _maybe_load_sellers(args) -> dict | None:
    """Return a sellers bundle if --sellers-json or --product-url was given.

    Order of precedence (cheap → expensive):
        1. --sellers-json <path>        (zero network; instant)
        2. --product-url <ozon url>     (CloakBrowser fetch; ~15-30s)
        3. neither                      (None; calc falls back to --market-price)

    Network errors are swallowed with a stderr warning so the calculator still
    produces a number — the user just won't see the 跟卖 section.
    """
    sj = getattr(args, "sellers_json", None)
    if sj:
        try:
            return json.loads(Path(sj).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"warn: --sellers-json {sj!r} unreadable: {exc}", file=sys.stderr)
            return None

    url = getattr(args, "product_url", None)
    if not url:
        return None
    try:
        # Defer import: only paid for when actually fetching
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "ozon-scraper"))
        from ozon_scraper.sellers import fetch_sellers
    except ImportError as exc:
        print(
            f"warn: --product-url given but ozon_scraper not importable ({exc}); "
            f"falling back to --market-price",
            file=sys.stderr,
        )
        return None

    print(f"[*] fetching sellers data from {url} …", file=sys.stderr)
    try:
        # We only need min_seller_price for Price Index; skip the parent
        # product page fetch since it adds ~15s and isn't used here.
        return fetch_sellers(url, include_all=False)
    except Exception as exc:
        print(
            f"warn: sellers fetch failed ({type(exc).__name__}: {exc}); "
            f"falling back to --market-price",
            file=sys.stderr,
        )
        return None

# Ozon-specific adapter: pulls commission & shipping from
# tools/ozon-fees-parser/data/ozon-fees.json (derived from official XLSX).
# Imported lazily so non-Ozon paths don't pay for it.
try:
    from . import ozon_fees as _ozon_fees  # type: ignore  # when run as package
except ImportError:
    import ozon_fees as _ozon_fees  # type: ignore  # when run as script

# ═══════════════════════════════════════════════════════════════════
# 配置加载 & 汇率获取
# ═══════════════════════════════════════════════════════════════════

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"配置文件不存在: {CONFIG_PATH}\n请先创建 params.json")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def try_fetch_fx(config: dict) -> bool:
    """尝试从 API 获取实时汇率，成功则更新 config 并写回文件。"""
    try:
        url = "https://open.er-api.com/v6/latest/CNY"
        req = urllib.request.Request(url, headers={"User-Agent": "kuajing-calc/3.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        if data.get("result") != "success":
            return False
        rates = data["rates"]
        config["exchange_rates"] = {
            "USD_CNY": round(1 / rates["USD"], 4),
            "RUB_CNY": round(1 / rates["RUB"], 6),
            "THB_CNY": round(1 / rates["THB"], 4),
            "MYR_CNY": round(1 / rates["MYR"], 4),
            "IDR_CNY": round(1 / rates["IDR"], 8),
        }
        config["_meta"]["fx_fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_config(config)
        return True
    except Exception:
        return False


def get_fx_rate(config: dict, currency: str) -> float:
    """返回 1 CNY = ? 外币。"""
    key = f"{currency}_CNY"
    cny_per_foreign = config["exchange_rates"].get(key, 1.0)
    if cny_per_foreign == 0:
        return 1.0
    return 1.0 / cny_per_foreign


# ═══════════════════════════════════════════════════════════════════
# 运费阶梯 & 体积重
# ═══════════════════════════════════════════════════════════════════

def calc_shipping(brackets: list, weight: float) -> float:
    """根据阶梯表计算运费。brackets 格式: [[max_g, price], ..., [null, per_g_rate]]"""
    for i, (max_w, price) in enumerate(brackets):
        if max_w is None:
            # 最后一项：超重线性外推
            prev_max = brackets[i - 1][0]
            prev_price = brackets[i - 1][1]
            return prev_price + (weight - prev_max) * price
        if weight <= max_w:
            return price
    # 不应到达
    return brackets[-2][1]


def calc_volume_weight(length: float, width: float, height: float) -> float:
    """体积重(g) = L(cm) × W(cm) × H(cm) / 6"""
    return length * width * height / 6.0


# ═══════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CalcInput:
    cost: float
    weight: float
    billable_weight: float
    volume_weight: float | None
    category: str
    platform: str
    price: float | None
    market_price: float | None
    # 费率
    commission: float
    return_rate: float
    return_handling: float
    payment_fee: float
    ship_base: float            # 阶梯运费（不含旺季）
    promo_discount: float
    # 现实校准
    ad_pct: float
    factory_loss: float
    warehouse_error: float
    malicious_return: float
    fx_buffer: float
    affiliate_pct: float
    seasonal_surcharge: float
    # 额外成本
    domestic_ship: float
    packing_fee: float
    import_tax: float
    # Ozon-specific（rFBS / FBP）
    fulfillment: str = "rfbs"          # rfbs | fbp（仅 platform=ozon 时生效）
    settlement_fee: float = 0.0        # 跨境收款代理费（第三方支付）
    pickup_fee_per_order: float = 0.0  # rFBS 揽收费 ¥/单（不满足免费阈值时）
    sellers_bundle: dict | None = None  # ozon_scraper.sellers 输出（如果抓了）
    # 元信息
    explicit_overrides: dict = field(default_factory=dict)
    commission_source: str | None = None     # "Tarifs_CN_*.xlsx" 或 "params.json"
    shipping_source: str | None = None       # "China_post_*.xlsx" 或 "params.json"
    market_price_source: str | None = None   # "sellers_min" | "--market-price" | None


@dataclass
class CalcResult:
    inputs: dict
    # 重量
    billable_weight: float
    volume_weight: float | None
    # 成本拆解
    ship_effective: float       # ship_base × (1 + seasonal)
    fixed_cost: float           # cost + domestic + packing + ship_eff + import_tax
    effective_handling: float
    # 费率
    total_loss_rate: float
    revenue_coef: float
    # 结果
    breakeven_cny: float
    target_cny: float
    markup_min: float
    markup_target: float
    ship_pct_of_breakeven: float
    target_profit_abs: float    # 推荐售价下每单利润
    # 退货抗性
    return_loss_per: float      # 退1单亏多少
    orders_to_cover: float      # 退1单要几单补回来
    # 对比
    naive_breakeven_cny: float
    # 按用户售价
    profit: float | None
    margin: float | None
    verdict: str | None
    # 竞品价
    market_profit: float | None
    market_margin: float | None
    market_verdict: str | None
    # Ozon Price Index（仅 platform=ozon 且给了 market_price 时填）
    price_index: float | None
    price_index_level: str | None       # green / yellow / red / red_forced
    price_index_label: str | None       # 🟢 有利 / 🟡 中等 / 🔴 不利 / 🔴🔴 强制不利
    search_boost: float | None          # 0.075 / 0.05 / 0
    price_for_green: float | None       # 进绿区的目标价 = market × green_max
    price_for_yellow: float | None      # 进黄区的目标价 = market × yellow_max
    # 诊断
    diagnostics: list[str]


# ═══════════════════════════════════════════════════════════════════
# 核心计算
# ═══════════════════════════════════════════════════════════════════

def _round(x, n=2):
    return float(Decimal(str(x)).quantize(
        Decimal("0.01") if n == 2 else Decimal(f"1e-{n}"),
        rounding=ROUND_HALF_UP,
    ))


def resolve_input(args, config: dict, platform_override=None, category_override=None) -> CalcInput:
    category = category_override or args.category or "通用"
    platform = platform_override or args.platform or "all"
    if platform == "all":
        platform = ALL_PLATFORMS[0]  # shouldn't happen in resolve, caller loops

    cats = config["categories"]
    plats = config["platforms"]
    comm_table = config["commission"]
    ship_table = config["shipping_brackets"]
    reality = config["reality_defaults"]

    if category not in cats:
        sys.exit(f"未知类目「{category}」。可选：{list(cats.keys())}")
    if platform not in plats:
        sys.exit(f"未知平台「{platform}」。可选：{list(plats.keys())}")

    cat = cats[category]
    plat = plats[platform]

    # 退货率：优先从 platform×category 2D 表读取，回退到 category 默认
    ret_table = config.get("return_rate", {})
    plat_ret = ret_table.get(platform, {})
    default_return_rate = plat_ret.get(category, cat.get("return_rate", 0.07))

    # 体积重
    volume_weight = None
    if args.length and args.width and args.height:
        volume_weight = calc_volume_weight(args.length, args.width, args.height)
    billable_weight = max(args.weight, volume_weight) if volume_weight else args.weight

    # 阶梯运费
    ship_base_default = calc_shipping(ship_table[platform], billable_weight)

    overrides = {}

    def take(default, override, name):
        if override is not None:
            overrides[name] = override
            return override
        return default

    commission_default = comm_table[platform].get(category, 0.08)
    commission_source: str | None = "params.json"

    # ── Sellers integration (Ozon only) ───────────────────────────────────
    # If user gave --product-url / --sellers-json, fetch跟卖 data and override
    # market_price with the cheapest seller's price. This makes the Price Index
    # check use real competition data instead of a manually supplied number.
    sellers_bundle: dict | None = None
    market_price_source: str | None = None
    if platform == "ozon":
        sellers_bundle = _maybe_load_sellers(args)
        if sellers_bundle:
            rub_cny = config["exchange_rates"].get("RUB_CNY", 0.0927)
            min_rub = sellers_bundle.get("price_min_rub")
            if min_rub is not None and rub_cny > 0:
                derived_market_cny = round(min_rub * rub_cny, 2)
                if args.market_price is None:
                    args.market_price = derived_market_cny
                    market_price_source = (
                        f"sellers_min ({min_rub} ₽ × {rub_cny} = ¥{derived_market_cny})"
                    )
                else:
                    market_price_source = (
                        f"--market-price (sellers_min would be ¥{derived_market_cny})"
                    )
        elif args.market_price is not None:
            market_price_source = "--market-price"

    # Ozon: override commission from official XLSX (Tarifs_CN) — selects price
    # tier from market_price (or middle tier if unknown). FBP gets a 1pp lower
    # rate than rFBS per official table.
    fulfillment = getattr(args, "fulfillment", None) or "rfbs"
    if platform == "ozon":
        market_rub = None
        if args.market_price is not None:
            rub_cny = config["exchange_rates"].get("RUB_CNY", 0.0927)
            if rub_cny > 0:
                market_rub = args.market_price / rub_cny
        rate, source = _ozon_fees.lookup_commission(
            fulfillment=fulfillment,
            coarse_category=category,
            market_price_rub=market_rub,
            fallback=commission_default,
        )
        commission_default = rate
        if source:
            commission_source = (
                f"{source['source_file']}#{source['sub_zh']}#{source['tier_label']}"
            )

    commission      = take(commission_default,                       args.commission,       "commission")
    return_rate     = take(default_return_rate,                       args.return_rate,      "return_rate")
    return_handling = take(cat["return_handling"],                    args.return_handling,  "return_handling")
    payment_fee     = take(plat["payment_fee"],                      args.payment_fee,      "payment_fee")
    ship_base       = take(ship_base_default,                        args.ship,             "ship")
    shipping_source: str | None = "params.json"

    # Ozon: override shipping from China_post or FBP_China XLSX when not
    # explicitly overridden via --ship and a valid route exists.
    if platform == "ozon" and args.ship is None:
        market_rub_for_ship = None
        if args.market_price is not None:
            rub_cny = config["exchange_rates"].get("RUB_CNY", 0.0927)
            if rub_cny > 0:
                market_rub_for_ship = args.market_price / rub_cny
        if fulfillment == "rfbs":
            route = _ozon_fees.lookup_rfbs_china_post(
                weight_g=billable_weight,
                market_price_rub=market_rub_for_ship,
                mode="ground",
            )
            if route and route.get("computed_cost_cny") is not None:
                ship_base = route["computed_cost_cny"]
                shipping_source = f"{route['name']} (China Post)"
        elif fulfillment == "fbp":
            carrier = _ozon_fees.lookup_fbp_china(
                weight_g=billable_weight,
                market_price_rub=market_rub_for_ship,
            )
            if carrier and carrier.get("computed_cost_cny") is not None:
                ship_base = carrier["computed_cost_cny"]
                shipping_source = f"{carrier['delivery_method']} (FBP)"
    promo_discount  = take(plat["promo_discount"],                   args.promo_discount,   "promo_discount")
    ad_pct          = take(reality["ad_pct"],                        args.ad_pct,           "ad_pct")
    factory_loss    = take(reality["factory_loss"],                   args.factory_loss,     "factory_loss")
    warehouse_error = take(reality["warehouse_error"],               args.warehouse_error,  "warehouse_error")
    malicious_return= take(reality["malicious_return"],              args.malicious_return, "malicious_return")
    fx_buffer       = take(plat["fx_buffer"],                        args.fx_buffer,        "fx_buffer")
    affiliate_pct   = take(reality["affiliate_pct"],                 args.affiliate_pct,    "affiliate_pct")
    seasonal        = take(reality["seasonal_surcharge"],            args.seasonal_surcharge,"seasonal_surcharge")
    domestic_ship   = take(reality["domestic_ship"],                  args.domestic_ship,    "domestic_ship")
    packing_fee     = take(reality["packing_fee"],                   args.packing_fee,      "packing_fee")
    import_tax      = take(reality["import_tax"],                    args.import_tax,       "import_tax")

    # rFBS-only addons: settlement fee (cross-border 3rd-party remittance) +
    # pickup surcharge. Both default to 0 for non-Ozon platforms.
    settlement_default = 0.0
    pickup_default = 0.0
    if platform == "ozon":
        rfbs_addons = config.get("rfbs_addons", {})
        settlement_default = rfbs_addons.get("settlement_fee", 0.011)
        pickup_fee_cfg = rfbs_addons.get("pickup_fee_per_order", 20.0)
        waive_pieces = rfbs_addons.get("pickup_waive_min_pieces", 50)
        waive_kg = rfbs_addons.get("pickup_waive_min_kg", 10)
        # Auto-waive when monthly orders ≥50 OR single package ≥10kg
        mo = getattr(args, "monthly_orders", None) or 0
        if mo >= waive_pieces or args.weight / 1000.0 >= waive_kg:
            pickup_default = 0.0
        else:
            pickup_default = pickup_fee_cfg if fulfillment == "rfbs" else 0.0

    settlement_fee = take(settlement_default, getattr(args, "settlement_fee", None), "settlement_fee")
    pickup_fee     = take(pickup_default,     getattr(args, "pickup_fee", None),     "pickup_fee")

    return CalcInput(
        cost=args.cost, weight=args.weight,
        billable_weight=billable_weight, volume_weight=volume_weight,
        category=category, platform=platform,
        price=args.price, market_price=args.market_price,
        commission=commission, return_rate=return_rate,
        return_handling=return_handling, payment_fee=payment_fee,
        ship_base=ship_base, promo_discount=promo_discount,
        ad_pct=ad_pct, factory_loss=factory_loss,
        warehouse_error=warehouse_error, malicious_return=malicious_return,
        fx_buffer=fx_buffer, affiliate_pct=affiliate_pct,
        seasonal_surcharge=seasonal, domestic_ship=domestic_ship,
        packing_fee=packing_fee, import_tax=import_tax,
        fulfillment=fulfillment,
        settlement_fee=settlement_fee,
        pickup_fee_per_order=pickup_fee,
        sellers_bundle=sellers_bundle,
        explicit_overrides=overrides,
        commission_source=commission_source,
        shipping_source=shipping_source,
        market_price_source=market_price_source,
    )


def calculate(inp: CalcInput, config: dict) -> CalcResult:
    # 实际运费（含旺季附加）
    ship_eff = inp.ship_base * (1 + inp.seasonal_surcharge)

    # 固定成本（rFBS 揽收附加费按单计入）
    fixed_cost = (
        inp.cost
        + inp.domestic_ship
        + inp.packing_fee
        + ship_eff
        + inp.import_tax
        + inp.pickup_fee_per_order
    )

    # 损失率
    total_loss = inp.return_rate + inp.malicious_return + inp.factory_loss + inp.warehouse_error

    # 有效退货处理（工厂吞损不产生 handling）
    eff_handling = (inp.return_rate + inp.malicious_return + inp.warehouse_error) * inp.return_handling

    # 收入系数 = (1 - 活动折扣) × (1 - 佣金 - 平台收款 - 跨境结算 - 广告 - fx - 达人)
    # NOTE: settlement_fee 是第三方支付（PingPong/连连/PandaPay）跨境收款代理费，
    # 跟 payment_fee（Ozon 平台 0.4%）分列，两者都扣销售额。
    fee_coef = (
        1
        - inp.commission
        - inp.payment_fee
        - inp.settlement_fee
        - inp.ad_pct
        - inp.fx_buffer
        - inp.affiliate_pct
    )
    revenue_coef = (1 - inp.promo_discount) * fee_coef

    margin_coef = (1 - total_loss) * revenue_coef
    if margin_coef <= 0:
        sys.exit("参数不合理：(1-损失率)×收入系数 <= 0，无法盈利。")

    p_min = (fixed_cost + eff_handling) / margin_coef
    margin_target = config.get("margin_target", 0.30)
    p_target = p_min / (1 - margin_target)

    # 推荐售价下每单利润
    target_profit = (1 - total_loss) * p_target * revenue_coef - fixed_cost - eff_handling

    # 裸公式保本（只算基础：进价+运费+基础退货，不含 v2/v3 额外因子）
    naive_loss = inp.return_rate
    naive_rev = 1 - inp.commission - inp.payment_fee
    naive_handling = inp.return_rate * inp.return_handling
    naive_fixed = inp.cost + inp.ship_base  # 不含国内运费/包装/旺季/进口税
    naive_p_min = (naive_fixed + naive_handling) / ((1 - naive_loss) * naive_rev) if ((1 - naive_loss) * naive_rev) > 0 else p_min

    ship_pct = ship_eff / p_min if p_min > 0 else 0

    # ── 诊断 ──
    diagnostics = []

    if p_min / inp.cost < 3:
        diagnostics.append(f"⚠️ 保本加价倍率 {p_min/inp.cost:.1f}x < 3x，抗波动薄，议价或换品。")

    if ship_pct > 0.40:
        diagnostics.append(f"⚠️ 运费占保本价 {ship_pct*100:.0f}%(>40%)，物流吃利润太多。")
    elif ship_pct > 0.25 and inp.billable_weight > 300:
        diagnostics.append(f"💡 运费占比 {ship_pct*100:.0f}%，{inp.billable_weight:g}g 注意核对实重 vs 体积重。")

    if inp.return_rate > 0.10:
        diagnostics.append(f"⚠️ 退货率 {inp.return_rate*100:.0f}% 偏高，绿区品类应 <7%。")

    if inp.billable_weight > 500 and inp.platform == "ozon" and inp.fulfillment == "rfbs":
        diagnostics.append(
            f"💡 {inp.billable_weight:g}g >500g 超中国邮政上限，"
            f"已自动切到商业承运商；或考虑 --fulfillment fbp 走合作仓。"
        )

    if inp.platform == "ozon" and p_min < 27:
        diagnostics.append(f"💡 保本 <300₽，Ozon 低价保护佣金可能更优。")

    # Cancellation/penalty awareness — see commissions__ozon-fees__fines.md
    # Not folded into P_min because cancellation rate is operational (not
    # price-driven), but the user should price in a safety margin if their
    # error_index trends high.
    if inp.platform == "ozon":
        diagnostics.append(
            "⚠️ Ozon 取消率罚款：4-10%→商品价×4.5% / 10-20%→×9% / "
            ">20%→×13.5%（fines.md）；rFBS 卖家自发要把 SLA 守住。"
        )
        # ≤5000 ₽ free destruction note (cancel-by-customer.md L34)
        rub_cny = config["exchange_rates"].get("RUB_CNY", 0.0927)
        threshold_cny = 5000 * rub_cny if rub_cny else 460
        if p_min <= threshold_cny:
            diagnostics.append(
                f"💡 保本 ¥{p_min:.0f} ≤ ¥{threshold_cny:.0f}（5000₽），"
                f"取消订单可免费销毁，退货成本低。"
            )

    if inp.volume_weight and inp.volume_weight > inp.weight:
        diagnostics.append(f"📐 体积重 {inp.volume_weight:.0f}g > 实重 {inp.weight:g}g，按体积重 {inp.billable_weight:.0f}g 计费。")

    reality_uplift = (p_min - naive_p_min) / naive_p_min if naive_p_min > 0 else 0
    if reality_uplift > 0.05:
        diagnostics.append(f"📊 现实校准抬升保本价 +{reality_uplift*100:.0f}%（¥{naive_p_min:.1f}→¥{p_min:.1f}）。")

    if inp.ad_pct > 0:
        diagnostics.append(f"💸 已计入广告 {inp.ad_pct*100:.0f}%。")
    if inp.affiliate_pct > 0:
        diagnostics.append(f"💸 已计入达人佣金 {inp.affiliate_pct*100:.0f}%。")
    if inp.seasonal_surcharge > 0:
        diagnostics.append(f"📦 旺季附加 +{inp.seasonal_surcharge*100:.0f}%，运费 ¥{inp.ship_base:.1f}→¥{ship_eff:.1f}。")
    if inp.platform == "temu_y2":
        diagnostics.append(f"💡 Temu Y2 供货价模式：此价格=你的供货价，消费者价由平台加价（通常 1.3-1.5x）。")

    # ── 按用户售价 ──
    profit = margin = verdict = None
    if inp.price is not None:
        profit = (1 - total_loss) * inp.price * revenue_coef - fixed_cost - eff_handling
        margin = profit / inp.price if inp.price > 0 else 0
        if profit < 0:
            verdict = "❌ 亏损"
            diagnostics.append(f"❌ 售价 ¥{inp.price:.0f} 每单亏 ¥{-profit:.1f}，至少 ¥{p_min:.1f}。")
        elif margin < 0.15:
            verdict = "⚠️ 紧绷"
            diagnostics.append(f"⚠️ 毛利 {margin*100:.0f}% <15%，风险高。")
        elif margin < 0.30:
            verdict = "✅ 盈利（中等）"
        else:
            verdict = "✅ 盈利（健康）"
            diagnostics.append(f"✅ 毛利 {margin*100:.0f}% ≥30%，可上架。")

    # ── 竞品售价 ──
    market_profit = market_margin = market_verdict = None
    if inp.market_price is not None:
        market_profit = (1 - total_loss) * inp.market_price * revenue_coef - fixed_cost - eff_handling
        market_margin = market_profit / inp.market_price if inp.market_price > 0 else 0
        if inp.market_price < p_min:
            market_verdict = "❌ 低于保本"
            diagnostics.append(f"❌ 竞品价 ¥{inp.market_price:.0f} < 保本 ¥{p_min:.1f}，该平台做不了。")
        elif market_margin < 0.15:
            market_verdict = "⚠️ 利润薄"
            diagnostics.append(f"⚠️ 按竞品价 ¥{inp.market_price:.0f} 毛利仅 {market_margin*100:.0f}%。")
        else:
            market_verdict = "✅ 可竞争"
            diagnostics.append(f"✅ 按竞品价 ¥{inp.market_price:.0f} 毛利 {market_margin*100:.0f}%，有空间。")

    # ── Ozon Price Index（关键：决定搜索曝光加权，详见 ozon/pricing-rules.md §1） ──
    price_index = price_index_level = price_index_label = None
    search_boost = price_for_green = price_for_yellow = None
    if inp.platform == "ozon" and inp.market_price is not None and inp.market_price > 0:
        pi_cfg = config.get("ozon_price_index", {
            "green_max": 1.02, "yellow_max": 1.05, "red_force_threshold": 1.30,
            "boost_green": 0.075, "boost_yellow": 0.05, "boost_red": 0.0,
        })
        price_index = p_target / inp.market_price
        price_for_green = inp.market_price * pi_cfg["green_max"]
        price_for_yellow = inp.market_price * pi_cfg["yellow_max"]
        if price_index >= pi_cfg["red_force_threshold"]:
            price_index_level = "red_forced"
            price_index_label = "🔴🔴 强制不利"
            search_boost = pi_cfg["boost_red"]
            diagnostics.append(
                f"🔴🔴 Price Index {price_index:.2f} ≥ 1.30，强制 Red：曝光归零。"
                f"必须降到 ≤ ¥{price_for_yellow:.1f}（黄）或 ¥{price_for_green:.1f}（绿）。"
            )
        elif price_index > pi_cfg["yellow_max"]:
            price_index_level = "red"
            price_index_label = "🔴 不利"
            search_boost = pi_cfg["boost_red"]
            diagnostics.append(
                f"🔴 Price Index {price_index:.2f} 在 Red 区（>1.05）：无搜索加权。"
                f"建议降到 ¥{price_for_green:.1f}（绿+7.5%曝光）或 ¥{price_for_yellow:.1f}（黄+5%）。"
            )
        elif price_index > pi_cfg["green_max"]:
            price_index_level = "yellow"
            price_index_label = "🟡 中等"
            search_boost = pi_cfg["boost_yellow"]
            diagnostics.append(
                f"🟡 Price Index {price_index:.2f} 黄区：+5% 曝光。"
                f"再降 ¥{(p_target - price_for_green):.1f} 到 ¥{price_for_green:.1f} 可入绿区（+7.5%）。"
            )
        else:
            price_index_level = "green"
            price_index_label = "🟢 有利"
            search_boost = pi_cfg["boost_green"]
            diagnostics.append(
                f"🟢 Price Index {price_index:.2f} 绿区：+7.5% 搜索加权 + '就是这个价'标签。"
            )

    # ── 退货抗性 ──
    # 退1单亏多少 = 固定成本 + 退货处理费（货白寄了，钱全没了）
    return_loss_per = fixed_cost + inp.return_handling
    # 成功1单赚多少（毛利，不含退货统计摊薄）
    gross_profit_per = p_target * revenue_coef - fixed_cost if p_target * revenue_coef > fixed_cost else 0.01
    orders_to_cover = return_loss_per / gross_profit_per if gross_profit_per > 0 else 999

    if orders_to_cover > 5:
        diagnostics.append(f"🚨 退1单要 {orders_to_cover:.1f} 单才能补回（亏 ¥{return_loss_per:.0f}/退），风险极高。")
    elif orders_to_cover > 3:
        diagnostics.append(f"⚠️ 退1单要 {orders_to_cover:.1f} 单补回（亏 ¥{return_loss_per:.0f}/退），利润缓冲偏薄。")

    if not diagnostics:
        diagnostics.append("✅ 各项参数均在合理区间。")

    return CalcResult(
        inputs=asdict(inp),
        billable_weight=inp.billable_weight,
        volume_weight=inp.volume_weight,
        ship_effective=_round(ship_eff),
        fixed_cost=_round(fixed_cost),
        effective_handling=_round(eff_handling),
        total_loss_rate=_round(total_loss, 4),
        revenue_coef=_round(revenue_coef, 4),
        breakeven_cny=_round(p_min),
        target_cny=_round(p_target),
        markup_min=_round(p_min / inp.cost, 2),
        markup_target=_round(p_target / inp.cost, 2),
        ship_pct_of_breakeven=_round(ship_pct, 4),
        target_profit_abs=_round(target_profit),
        return_loss_per=_round(return_loss_per),
        orders_to_cover=_round(orders_to_cover, 1),
        naive_breakeven_cny=_round(naive_p_min),
        profit=_round(profit) if profit is not None else None,
        margin=_round(margin, 4) if margin is not None else None,
        verdict=verdict,
        market_profit=_round(market_profit) if market_profit is not None else None,
        market_margin=_round(market_margin, 4) if market_margin is not None else None,
        market_verdict=market_verdict,
        price_index=_round(price_index, 4) if price_index is not None else None,
        price_index_level=price_index_level,
        price_index_label=price_index_label,
        search_boost=_round(search_boost, 4) if search_boost is not None else None,
        price_for_green=_round(price_for_green) if price_for_green is not None else None,
        price_for_yellow=_round(price_for_yellow) if price_for_yellow is not None else None,
        diagnostics=diagnostics,
    )


# ═══════════════════════════════════════════════════════════════════
# 批量计算（全平台 × 全类目 / 单类目 / 单平台）
# ═══════════════════════════════════════════════════════════════════

def run_calculations(args, config: dict) -> dict:
    """返回嵌套结构 {category: {platform: CalcResult_dict}}。"""
    platform_arg = args.platform or "all"
    category_arg = args.category  # None = 全类目

    platforms = ALL_PLATFORMS if platform_arg == "all" else [platform_arg]
    if category_arg:
        categories = [category_arg]
    else:
        # 全类目（排除"通用"放最后）
        cats = list(config["categories"].keys())
        categories = [c for c in cats if c != "通用"] + ["通用"]

    results = {}
    # Stash the live CalcInput objects so main() doesn't have to re-resolve
    # (re-resolving would re-run _maybe_load_sellers, double-fetch the modal,
    # and mis-label the market_price_source because args has been mutated).
    inputs: dict[str, dict[str, "CalcInput"]] = {}
    for cat in categories:
        results[cat] = {}
        inputs[cat] = {}
        for plat in platforms:
            inp = resolve_input(args, config, platform_override=plat, category_override=cat)
            res = calculate(inp, config)
            results[cat][plat] = asdict(res)
            inputs[cat][plat] = inp

    return {
        "_inputs": inputs,
        "_meta": {
            "cost": args.cost,
            "weight": args.weight,
            "length": args.length,
            "width": args.width,
            "height": args.height,
            "price": args.price,
            "market_price": args.market_price,
            "platforms": platforms,
            "categories": categories,
            "fx_rates": config["exchange_rates"],
            "fx_fetched_at": config["_meta"].get("fx_fetched_at"),
        },
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════════
# Pretty 输出
# ═══════════════════════════════════════════════════════════════════

def _format_sellers_section(inp: CalcInput, res: CalcResult, fx: float) -> str:
    """Render the 【跟卖分析】 section. Caller already checked sellers_bundle exists."""
    b = inp.sellers_bundle
    lines = ["\n【跟卖分析】"]
    lines.append(f"  跟卖数量：     {b['n_sellers']} 家（{b['n_with_price']} 有报价）")
    cur = b.get("current_seller")
    cur_rank = b.get("current_rank")
    if cur:
        rank_txt = f"，排名 {cur_rank}/{b['n_with_price']}" if cur_rank else ""
        lines.append(f"  页面卖家：     {cur}{rank_txt}")
    pmin, pmed, pmax = b["price_min_rub"], b["price_median_rub"], b["price_max_rub"]
    # Convert RUB → CNY  (fx = 1 CNY in foreign units, so foreign / fx = CNY)
    pmin_cny = pmin / max(fx, 1e-9) if pmin else None
    pmed_cny = pmed / max(fx, 1e-9) if pmed else None
    pmax_cny = pmax / max(fx, 1e-9) if pmax else None
    lines.append(
        f"  价格范围：     {pmin}-{pmax} ₽  "
        f"(¥{pmin_cny:.0f}-¥{pmax_cny:.0f}，中位 ¥{pmed_cny:.0f})"
    )
    cc = b.get("country_counts_zh") or b.get("country_counts") or {}
    if cc:
        parts = "  ".join(f"{k} {v}" for k, v in cc.items())
        lines.append(f"  国家分布：     {parts}")
    cities = b.get("city_top5_zh") or []
    if cities:
        parts = "、".join(f"{c} {n}" for c, n in cities[:5])
        lines.append(f"  Top5 城市：    {parts}")
    if inp.market_price_source:
        lines.append(f"  市场价来源：   {inp.market_price_source}")
    # Add a diagnostic: where would your breakeven place you?
    if pmin and inp.market_price is not None:
        # CNY → RUB: multiply by fx (fx = "1 CNY = N foreign", so cny * fx = rub)
        breakeven_rub = res.breakeven_cny * fx
        if breakeven_rub > pmax:
            verdict = "❌ 保本价超过最高跟卖，无戏"
        elif breakeven_rub > pmed:
            verdict = "⚠️ 保本价高于中位，只能跟尾部卖家"
        elif breakeven_rub > pmin:
            verdict = "✅ 保本价在中位以下，有竞争力"
        else:
            verdict = "🟢 保本价低于最低跟卖，可正面卷"
        lines.append(
            f"  保本排位：     {breakeven_rub:.0f} ₽（¥{res.breakeven_cny:.0f}）→ {verdict}"
        )
    return "\n".join(lines)


def format_single(inp: CalcInput, res: CalcResult, config: dict) -> str:
    plat = config["platforms"][inp.platform]
    fx = get_fx_rate(config, plat["currency"])
    sym = plat["symbol"]
    lines = []
    lines.append(f"\n🧮 盈亏测算 · {plat['display']} · {inp.category}")
    lines.append("=" * 60)

    lines.append(f"\n【输入】")
    lines.append(f"  1688 成本：    ¥{inp.cost:.2f}")
    lines.append(f"  计费重：       {inp.billable_weight:g}g" +
                 (f"  (实重 {inp.weight:g}g / 体积重 {inp.volume_weight:.0f}g)" if inp.volume_weight else ""))
    lines.append(f"  类目：         {inp.category}")
    if inp.platform == "ozon":
        lines.append(f"  平台：         {plat['display']}（履约 {inp.fulfillment}）")
    else:
        lines.append(f"  平台：         {plat['display']}")
    if inp.price is not None:
        lines.append(f"  当前售价：     ¥{inp.price:.2f}")
    if inp.market_price is not None:
        lines.append(f"  竞品售价：     ¥{inp.market_price:.2f}")

    lines.append(f"\n【固定成本（每单）】")
    lines.append(f"  采购：         ¥{inp.cost:.2f}")
    lines.append(f"  国内运费：     ¥{inp.domestic_ship:.2f}")
    lines.append(f"  包装费：       ¥{inp.packing_fee:.2f}")
    ship_suffix = ""
    if inp.seasonal_surcharge > 0:
        ship_suffix = f"  (含旺季 +{inp.seasonal_surcharge*100:.0f}%)"
    elif inp.shipping_source and inp.shipping_source != "params.json":
        ship_suffix = f"  ⟵ {inp.shipping_source}"
    lines.append(f"  国际运费：     ¥{res.ship_effective:.2f}{ship_suffix}")
    lines.append(f"  进口税：       ¥{inp.import_tax:.2f}")
    if inp.pickup_fee_per_order > 0:
        lines.append(f"  揽收附加：     ¥{inp.pickup_fee_per_order:.2f}  (rFBS 单包 <10kg)")
    lines.append(f"  ─── 合计固定：  ¥{res.fixed_cost:.2f}")

    lines.append(f"\n【费率】")
    if inp.commission_source and inp.commission_source != "params.json":
        lines.append(f"  佣金：         {inp.commission*100:.1f}%  ⟵ {inp.commission_source}")
    else:
        lines.append(f"  佣金：         {inp.commission*100:.1f}%")
    lines.append(f"  平台收款：     {inp.payment_fee*100:.2f}%  (Ozon 0.4% 等)")
    if inp.settlement_fee > 0:
        lines.append(f"  跨境结算：     {inp.settlement_fee*100:.2f}%  (PingPong/连连/PandaPay)")
    lines.append(f"  活动折扣：     {inp.promo_discount*100:.0f}%")
    lines.append(f"  广告占比：     {inp.ad_pct*100:.1f}%")
    lines.append(f"  达人佣金：     {inp.affiliate_pct*100:.1f}%")
    lines.append(f"  汇率 buffer：  {inp.fx_buffer*100:.1f}%")
    lines.append(f"  ─── 收入系数：  {res.revenue_coef*100:.1f}%")

    lines.append(f"\n【损失率】")
    lines.append(f"  退货 {inp.return_rate*100:.0f}% + 恶意退 {inp.malicious_return*100:.0f}% + 工厂 {inp.factory_loss*100:.0f}% + 仓错 {inp.warehouse_error*100:.0f}% = {res.total_loss_rate*100:.0f}%（成功率 {(1-res.total_loss_rate)*100:.0f}%）")

    lines.append(f"\n【结果】")
    lines.append(f"  💵 保本售价：  ¥{res.breakeven_cny}（{sym}{res.breakeven_cny * fx:.0f}）  加价 {res.markup_min}x")
    lines.append(f"  💰 推荐售价：  ¥{res.target_cny}（{sym}{res.target_cny * fx:.0f}）  加价 {res.markup_target}x  每单利润 ¥{res.target_profit_abs:.1f}")
    lines.append(f"  📐 裸公式保本：¥{res.naive_breakeven_cny}（校准抬升 {(res.breakeven_cny/res.naive_breakeven_cny-1)*100:+.0f}%）")

    if res.profit is not None:
        lines.append(f"\n【按售价 ¥{inp.price:.2f}】")
        lines.append(f"  利润 ¥{res.profit:+.2f}/单  毛利 {res.margin*100:.1f}%  {res.verdict}")

    if res.market_profit is not None:
        lines.append(f"\n【竞品价 ¥{inp.market_price:.2f}】")
        lines.append(f"  利润 ¥{res.market_profit:+.2f}/单  毛利 {res.market_margin*100:.1f}%  {res.market_verdict}")

    if inp.sellers_bundle:
        lines.append(_format_sellers_section(inp, res, fx))

    if res.price_index is not None:
        lines.append(f"\n【Ozon Price Index（曝光加权）】")
        lines.append(f"  推荐价 ¥{res.target_cny} / 竞品最低 ¥{inp.market_price:.0f} = {res.price_index:.2f}  {res.price_index_label}")
        lines.append(f"  搜索曝光加权：{res.search_boost*100:+.1f}%")
        lines.append(f"  入绿区上限：¥{res.price_for_green:.1f}（≤竞品×1.02）  入黄区上限：¥{res.price_for_yellow:.1f}（≤竞品×1.05）")

    lines.append(f"\n【诊断】")
    for d in res.diagnostics:
        lines.append(f"  {d}")
    lines.append("")
    return "\n".join(lines)


def format_matrix(data: dict, config: dict) -> str:
    """全类目 × 全平台矩阵输出。"""
    meta = data["_meta"]
    results = data["results"]
    categories = meta["categories"]
    platforms = meta["platforms"]
    lines = []

    lines.append(f"\n🧮 全类目盈亏矩阵")
    lines.append("=" * 60)
    lines.append(f"  进价 ¥{meta['cost']:.2f}  重量 {meta['weight']:g}g  目标毛利 {config.get('margin_target', 0.30)*100:.0f}%")
    if meta.get("price"):
        lines.append(f"  当前售价 ¥{meta['price']:.2f}")
    if meta.get("market_price"):
        lines.append(f"  竞品售价 ¥{meta['market_price']:.2f}")
    fx_time = meta.get("fx_fetched_at")
    lines.append(f"  汇率：{'实时 ' + fx_time if fx_time else '缓存（未联网）'}")
    lines.append("")

    # 平台显示名
    pnames = [config["platforms"][p]["display"] for p in platforms]
    col_w = max(12, max(len(n) for n in pnames) + 2)

    def header_row():
        return f"  {'类目':<10}" + "".join(f"{n:>{col_w}}" for n in pnames)

    def sep_row():
        return f"  {'─'*10}" + "".join(f"{'─'*col_w}" for _ in platforms)

    # ── 保本售价 ──
    lines.append("── 保本售价 (¥) ──")
    lines.append(header_row())
    lines.append(sep_row())
    for cat in categories:
        vals = [f"¥{results[cat][p]['breakeven_cny']:>7}" for p in platforms]
        lines.append(f"  {cat:<10}" + "".join(f"{v:>{col_w}}" for v in vals))
    lines.append("")

    # ── 推荐售价 ──
    lines.append("── 推荐售价 (¥, 30%毛利) ──")
    lines.append(header_row())
    lines.append(sep_row())
    for cat in categories:
        vals = [f"¥{results[cat][p]['target_cny']:>7}" for p in platforms]
        lines.append(f"  {cat:<10}" + "".join(f"{v:>{col_w}}" for v in vals))
    lines.append("")

    # ── 每单利润 ──
    lines.append("── 每单利润 (¥, 推荐售价下) ──")
    lines.append(header_row())
    lines.append(sep_row())
    for cat in categories:
        vals = [f"¥{results[cat][p]['target_profit_abs']:>+6.1f}" for p in platforms]
        lines.append(f"  {cat:<10}" + "".join(f"{v:>{col_w}}" for v in vals))
    lines.append("")

    # ── 佣金率 ──
    lines.append("── 佣金率 ──")
    lines.append(header_row())
    lines.append(sep_row())
    comm = config["commission"]
    for cat in categories:
        vals = [f"{comm[p].get(cat, 0)*100:>5.0f}%" for p in platforms]
        lines.append(f"  {cat:<10}" + "".join(f"{v:>{col_w}}" for v in vals))
    lines.append("")

    # ── 如果有售价或竞品价 ──
    if meta.get("price"):
        lines.append(f"── 按售价 ¥{meta['price']:.0f} 每单利润 ──")
        lines.append(header_row())
        lines.append(sep_row())
        for cat in categories:
            row_vals = []
            for p in platforms:
                r = results[cat][p]
                if r["profit"] is not None:
                    row_vals.append(f"¥{r['profit']:>+6.1f}")
                else:
                    row_vals.append(f"{'N/A':>7}")
            lines.append(f"  {cat:<10}" + "".join(f"{v:>{col_w}}" for v in row_vals))
        lines.append("")

    if meta.get("market_price"):
        lines.append(f"── 竞品价 ¥{meta['market_price']:.0f} 每单利润 ──")
        lines.append(header_row())
        lines.append(sep_row())
        for cat in categories:
            row_vals = []
            for p in platforms:
                r = results[cat][p]
                if r["market_profit"] is not None:
                    row_vals.append(f"¥{r['market_profit']:>+6.1f}")
                else:
                    row_vals.append(f"{'N/A':>7}")
            lines.append(f"  {cat:<10}" + "".join(f"{v:>{col_w}}" for v in row_vals))
        lines.append("")

    # ── 运费 ──
    lines.append("── 国际运费 (¥) ──")
    lines.append(header_row())
    lines.append(sep_row())
    # 运费相同（只看第一个类目即可，因为运费不分类目）
    first_cat = categories[0]
    vals = [f"¥{results[first_cat][p]['ship_effective']:>7.1f}" for p in platforms]
    lines.append(f"  {'(所有类目)':<10}" + "".join(f"{v:>{col_w}}" for v in vals))
    lines.append("")

    # ── 最优推荐 ──
    lines.append("── 推荐 ──")
    best_cat = best_plat = None
    best_profit = -999999
    for cat in categories:
        if cat == "通用":
            continue
        for p in platforms:
            tp = results[cat][p]["target_profit_abs"]
            if tp > best_profit:
                best_profit = tp
                best_cat = cat
                best_plat = p
    if best_cat:
        bp = config["platforms"][best_plat]["display"]
        lines.append(f"  🏆 最优组合：{best_cat} + {bp}（推荐售价下每单利润 ¥{best_profit:.1f}）")

    # 最差
    worst_cat = worst_plat = None
    worst_be = 0
    for cat in categories:
        if cat == "通用":
            continue
        for p in platforms:
            be = results[cat][p]["breakeven_cny"]
            if be > worst_be:
                worst_be = be
                worst_cat = cat
                worst_plat = p
    if worst_cat:
        wp = config["platforms"][worst_plat]["display"]
        lines.append(f"  ⚠️ 最高门槛：{worst_cat} + {wp}（保本 ¥{worst_be}）")

    lines.append("")
    return "\n".join(lines)


def format_all_platforms_single_cat(data: dict, config: dict) -> str:
    """全平台 × 单类目（和 v2 类似但更丰富）。"""
    meta = data["_meta"]
    results = data["results"]
    cat = meta["categories"][0]
    platforms = meta["platforms"]
    lines = []

    lines.append(f"\n🧮 4 平台盈亏测算 · {cat}")
    lines.append("=" * 60)
    lines.append(f"  进价 ¥{meta['cost']:.2f}  重量 {meta['weight']:g}g  类目 {cat}")
    fx_time = meta.get("fx_fetched_at")
    lines.append(f"  汇率：{'实时 ' + fx_time if fx_time else '缓存'}")
    lines.append("")

    for p in platforms:
        r = results[cat][p]
        plat = config["platforms"][p]
        fx = get_fx_rate(config, plat["currency"])
        sym = plat["symbol"]
        inp = r["inputs"]

        lines.append(f"── {plat['display']} ──")
        lines.append(f"  运费 ¥{r['ship_effective']:.1f}  佣金 {inp['commission']*100:.0f}%  活动折扣 {inp['promo_discount']*100:.0f}%  收入系数 {r['revenue_coef']*100:.1f}%")
        lines.append(f"  💵 保本 ¥{r['breakeven_cny']}（{sym}{r['breakeven_cny']*fx:.0f}）  加价 {r['markup_min']}x")
        lines.append(f"  💰 推荐 ¥{r['target_cny']}（{sym}{r['target_cny']*fx:.0f}）  加价 {r['markup_target']}x  利润 ¥{r['target_profit_abs']:.1f}/单")
        lines.append(f"  📐 裸公式 ¥{r['naive_breakeven_cny']}（校准 {(r['breakeven_cny']/r['naive_breakeven_cny']-1)*100:+.0f}%）")
        if r["profit"] is not None:
            lines.append(f"  📊 售价 ¥{inp['price']:.0f}：利润 ¥{r['profit']:+.1f}  毛利 {r['margin']*100:.0f}%  {r['verdict']}")
        if r["market_profit"] is not None:
            lines.append(f"  🏷️ 竞品 ¥{inp['market_price']:.0f}：利润 ¥{r['market_profit']:+.1f}  毛利 {r['market_margin']*100:.0f}%  {r['market_verdict']}")
        lines.append("")

    # 汇总表
    lines.append("── 汇总 ──")
    lines.append(f"  {'平台':<12} {'运费':>5} {'固定成本':>7} {'保本':>7} {'推荐':>7} {'利润/单':>7} {'加价':>5} {'运费占比':>7}")
    for p in platforms:
        r = results[cat][p]
        plat = config["platforms"][p]
        lines.append(f"  {plat['display']:<12} ¥{r['ship_effective']:>4.0f} ¥{r['fixed_cost']:>6.0f} ¥{r['breakeven_cny']:>6} ¥{r['target_cny']:>6} ¥{r['target_profit_abs']:>+5.1f} {r['markup_min']:>4}x {r['ship_pct_of_breakeven']*100:>5.0f}%")
    lines.append("")

    # 诊断
    all_diag = []
    for p in platforms:
        for d in results[cat][p]["diagnostics"]:
            tagged = f"[{config['platforms'][p]['display']}] {d}"
            if tagged not in all_diag:
                all_diag.append(tagged)
    if all_diag:
        lines.append("── 诊断 ──")
        for d in all_diag:
            lines.append(f"  {d}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def make_parser():
    p = argparse.ArgumentParser(
        description="跨境一件代发盈亏测算器 v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # 必填
    p.add_argument("--cost", type=float, help="1688 采购成本 ¥（必填）")
    p.add_argument("--weight", type=float, help="实际重量 g（必填）")
    # 范围
    p.add_argument("--category", type=str, default=None, help="类目（不填=全类目矩阵）")
    p.add_argument("--platform", type=str, default=None, help="平台: ali/temu_y2/tt_sea/ozon/all（默认 all）")
    # 可选输入
    p.add_argument("--price", type=float, default=None, help="当前售价 ¥")
    p.add_argument("--market-price", dest="market_price", type=float, default=None, help="竞品售价 ¥")
    # 体积重
    p.add_argument("--length", type=float, default=None, help="包装长 cm")
    p.add_argument("--width", type=float, default=None, help="包装宽 cm")
    p.add_argument("--height", type=float, default=None, help="包装高 cm")
    # 费率覆盖
    p.add_argument("--commission", type=float, default=None, help="覆盖佣金率")
    p.add_argument("--return-rate", dest="return_rate", type=float, default=None)
    p.add_argument("--return-handling", dest="return_handling", type=float, default=None)
    p.add_argument("--payment-fee", dest="payment_fee", type=float, default=None)
    p.add_argument("--ship", type=float, default=None, help="覆盖运费 ¥")
    p.add_argument("--promo-discount", dest="promo_discount", type=float, default=None, help="活动折扣率")
    # 新增成本
    p.add_argument("--domestic-ship", dest="domestic_ship", type=float, default=None, help="国内运费 ¥")
    p.add_argument("--packing-fee", dest="packing_fee", type=float, default=None, help="包装费 ¥")
    p.add_argument("--import-tax", dest="import_tax", type=float, default=None, help="进口税 ¥/单")
    # 现实校准
    p.add_argument("--ad-pct", dest="ad_pct", type=float, default=None)
    p.add_argument("--factory-loss", dest="factory_loss", type=float, default=None)
    p.add_argument("--warehouse-error", dest="warehouse_error", type=float, default=None)
    p.add_argument("--malicious-return", dest="malicious_return", type=float, default=None)
    p.add_argument("--fx-buffer", dest="fx_buffer", type=float, default=None)
    p.add_argument("--affiliate-pct", dest="affiliate_pct", type=float, default=None, help="达人佣金率")
    p.add_argument("--seasonal-surcharge", dest="seasonal_surcharge", type=float, default=None, help="旺季运费附加率")
    # 控制
    # Ozon-specific
    p.add_argument(
        "--fulfillment",
        choices=["rfbs", "fbp"],
        default="rfbs",
        help="Ozon 履约模式：rfbs(默认，卖家自配送) | fbp(合作伙伴仓库)",
    )
    p.add_argument(
        "--product-url",
        dest="product_url",
        default=None,
        help="Ozon 商品 URL；给了就自动抓跟卖 → 用最低跟卖价做 Price Index (~30s, 仅 ozon)",
    )
    p.add_argument(
        "--sellers-json",
        dest="sellers_json",
        default=None,
        help="跳过抓取，直接读取 ozon-scraper sellers 已生成的 JSON",
    )
    p.add_argument(
        "--fast-sellers",
        dest="fast_sellers",
        action="store_true",
        help="--product-url 时不抓父商品页（current_seller/current_rank 留空，省 15s）",
    )
    p.add_argument(
        "--settlement-fee",
        dest="settlement_fee",
        type=float,
        default=None,
        help="跨境收款代理费率（连连/PingPong/PandaPay 约 1.1%%；默认从 params 读）",
    )
    p.add_argument(
        "--pickup-fee",
        dest="pickup_fee",
        type=float,
        default=None,
        help="rFBS 揽收费 ¥/单（默认 ¥20，订单 ≥10kg 或 ≥50 票可豁免）",
    )
    p.add_argument(
        "--monthly-orders",
        dest="monthly_orders",
        type=int,
        default=None,
        help="月单量（≥50 时 rFBS 揽收费自动豁免）",
    )

    p.add_argument("--no-fetch-fx", dest="no_fetch_fx", action="store_true", help="不获取实时汇率")
    p.add_argument("--output", choices=["pretty", "json"], default="pretty")
    return p


def main():
    parser = make_parser()
    args = parser.parse_args()

    if args.cost is None or args.weight is None:
        parser.error("缺少必填参数：--cost 和 --weight")

    config = load_config()

    # 尝试获取实时汇率
    if not args.no_fetch_fx:
        fx_ok = try_fetch_fx(config)
        if not fx_ok:
            ts = config["_meta"].get("fx_fetched_at", "未知")
            print(f"⚠️ 汇率获取失败，使用缓存值（{ts}）", file=sys.stderr)

    data = run_calculations(args, config)

    if args.output == "json":
        # _inputs holds CalcInput objects (live references); drop before JSON
        public = {k: v for k, v in data.items() if k != "_inputs"}
        print(json.dumps(public, ensure_ascii=False, indent=2))
    else:
        meta = data["_meta"]
        cats = meta["categories"]
        plats = meta["platforms"]

        if len(cats) == 1 and len(plats) == 1:
            # 单平台 单类目 — reuse the CalcInput we already built (avoids
            # re-resolving and double-fetching sellers data).
            inp = data["_inputs"][cats[0]][plats[0]]
            res_dict = data["results"][cats[0]][plats[0]]
            res = CalcResult(**{k: v for k, v in res_dict.items() if k in CalcResult.__dataclass_fields__})
            print(format_single(inp, res, config))
        elif len(cats) == 1:
            # 全平台 单类目
            print(format_all_platforms_single_cat(data, config))
        else:
            # 全类目矩阵
            print(format_matrix(data, config))


if __name__ == "__main__":
    main()
