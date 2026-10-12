#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ozon 俄罗斯站跨境(RFBS, 中国卖家) 商品利润计算器
- 对比 ZTO(合作物流 Standard) 与 OGL(Ozon Global Logistics) 两个物流渠道的单件利润
- 推荐更省钱的物流渠道
- 推荐达到目标利润率的售价(二分求解)

用法(单商品):
    python calc_profit.py --price 129 --cost 36 --weight 450
    python calc_profit.py --price 452 --cost 311 --weight 750 --target-margin 10

用法(批量, JSON 文件):
    python calc_profit.py --file goods.json
    # goods.json = [{"name":"S3金属1只","price":129,"cost":36,"weight":450}, ...]

可选参数:
    --rate <汇率>            1 CNY = ? RUB, 默认 12.7154 (2026-10-09 新浪收盘)
    --commission <小数>      佣金率, 默认 0.17 (汽车用品 Car Products, RFBS 三档 12%/17%/17%, 默认值=17%档)
    --category <car|other>   car=汽车用品(默认, 自动按卢布档 12/17/17); other=固定用 --commission
    --target-margin <小数>   目标利润率, 默认 0.10
    --channel <all|zto|ogl>  只算指定渠道, 默认 all
    --json                   JSON 输出
"""

import argparse
import json
import sys

# ---------------- 费率数据(2026 核实的官方口径, 详见 references/rates.md) ----------------

# 评分组: (价值下限R, 价值上限R, 重量下限g, 重量上限g, 组名)
SCORING_GROUPS = [
    (1,     1500,   1,     500,    "Extra Small"),
    (1,     1500,   501,   30000,  "Budget"),
    (1501,  7000,   1,     2000,   "Small"),
    (1501,  7000,   2001,  30000,  "Big"),
    (7001,  250000, 1,     5000,   "Premium Small"),
    (7001,  250000, 5001,  30000,  "Premium Big"),
]

# 佣金(汽车用品 RFBS): 按货件卢布价值分档
CAR_COMMISSION_TIERS = [(1500, 0.12), (float("inf"), 0.17)]  # ≤1500R=12%, >1500R=17%

# ZTO(合作物流) Standard 档: fix + var/g
ZTO_STANDARD = {
    "Extra Small":   (3.12,  0.0364),
    "Budget":        (23.92, 0.026),
    "Small":         (16.64, 0.0364),
    "Big":           (37.44, 0.026),
    "Premium Small": (22.88, 0.0364),
    "Premium Big":   (64.48, 0.02912),
}

# OGL 运输服务费: fix + var/g
OGL_RATES = {
    "Extra Small":   (2.9,   0.0247),
    "Budget":        (22.25, 0.0164),
    "Small":         (15.48, 0.0242),
    "Big":           (34.82, 0.0164),
    "Premium Small": (21.28, 0.0242),
    "Premium Big":   (59.97, 0.0222),
}

# China Post to PUDO 渠道 —— 真实费率(用户提供 Ozon 物流产品表, 均限 1g-500g / 货值≤1500卢布)
# 陆运 WH Economy: 1.9元/件 + 26元/KG; 无赔偿/退回, 自提点取货
CHINA_POST_ECON = {"fix": 1.9, "per_kg": 26.0, "weight_max_g": 500, "value_max_rub": 1500,
                   "name": "ChinaPost-PUDO Eco(陆运)"}
# 空运 WH Standard: 1.9元/件 + 67元/KG; 限制同陆运
CHINA_POST_AIR = {"fix": 1.9, "per_kg": 67.0, "weight_max_g": 500, "value_max_rub": 1500,
                  "name": "ChinaPost-PUDO Std(空运)"}
CH_POST_NAME = CHINA_POST_ECON["name"]

AGENT_PCT = 0.02    # Ozon 电子服务/代理费 = 货件价值×2%, 封顶 15~200 卢布/件
AGENT_MIN = 15.0
AGENT_MAX = 200.0
CROSS_PCT = 0.0033  # 跨境国际代理服务费 = 货件价值×0.33% (2026-09-01 起, 无封顶, 签收后扣)


def scoring_group(rub, weight_g):
    for vmin, vmax, wmin, wmax, name in SCORING_GROUPS:
        if vmin <= rub <= vmax and wmin <= weight_g <= wmax:
            return name
    return "OutOfTable"


def commission_rate_car(rub):
    for threshold, rate in CAR_COMMISSION_TIERS:
        if rub <= threshold:
            return rate
    return CAR_COMMISSION_TIERS[-1][1]


def logistics_fee(channel, rub, weight_g, rate):
    """物流总成本(CNY): 承运/运输 + 2%代理 + 0.33%跨境"""
    if channel == "zto":
        grp = scoring_group(rub, weight_g)
        fix, var = ZTO_STANDARD.get(grp, (0.0, 0.0))
        ship = fix + var * weight_g
    elif channel == "ogl":
        grp = scoring_group(rub, weight_g)
        fix, var = OGL_RATES.get(grp, (0.0, 0.0))
        ship = fix + var * weight_g
    else:  # china_post(economy) / china_post_air(standard)
        cfg = CHINA_POST_ECON if channel == "china_post" else CHINA_POST_AIR
        grp = cfg["name"]
        ship = cfg["fix"] + cfg["per_kg"] * (weight_g / 1000)
    agent = max(AGENT_MIN, min(AGENT_MAX, rub * AGENT_PCT)) / rate
    cross = rub * CROSS_PCT / rate
    return grp, ship + agent + cross, ship, agent, cross


def calc_one(name, price, cost, weight_g, rate, category, custom_commission):
    rub = price * rate
    comm = price * (commission_rate_car(rub) if category == "car" else custom_commission)
    result = {"name": name, "price": price, "cost": cost, "weight_g": weight_g,
              "rub": round(rub, 1), "commission": round(comm, 2), "commission_rate":
              round(comm / price, 4), "channels": {}}
    best = None
    CP_CFG = {"china_post": CHINA_POST_ECON, "china_post_air": CHINA_POST_AIR}
    for ch in ("zto", "ogl", "china_post", "china_post_air"):
        if ch in CP_CFG and (weight_g > CP_CFG[ch]["weight_max_g"]
                             or rub > CP_CFG[ch]["value_max_rub"]):
            result["channels"][ch] = {"unavailable": True,
                                      "reason": "超出限重≤500g / 货值≤1500R"}
            continue
        grp, logi, ship, agent, cross = logistics_fee(ch, rub, weight_g, rate)
        profit = price - cost - comm - logi
        margin = profit / price if price else 0
        result["channels"][ch] = {
            "group": grp, "ship": round(ship, 2), "agent2pct": round(agent, 2),
            "cross033": round(cross, 2), "logistics": round(logi, 2),
            "total_cost": round(comm + logi, 2), "profit": round(profit, 2),
            "margin": round(margin * 100, 1),
        }
        if best is None or profit > best["profit"]:
            best = {"channel": ch, **result["channels"][ch]}
    result["best_channel"] = best["channel"]
    result["best_profit"] = best["profit"]
    result["best_margin"] = best["margin"]
    return result


def recommend_price(name, cost, weight_g, rate, category, custom_commission,
                    channel, target_margin):
    """在指定渠道下, 二分求达到目标利润率的最小售价(CNY)"""
    lo, hi = cost, cost * 10
    for _ in range(80):
        mid = (lo + hi) / 2
        c = calc_one(name, mid, cost, weight_g, rate, category, custom_commission)
        if c["channels"][channel]["margin"] >= target_margin * 100:
            hi = mid
        else:
            lo = mid
    return round(hi, 0)


def print_human(name, price, cost, weight_g, rate, category, custom_commission,
                channel, target_margin, out):
    c = calc_one(name, price, cost, weight_g, rate, category, custom_commission)
    line = "=" * 64
    print(line)
    print(f"{name} | 售价¥{price} | 进货¥{cost} | 重量{weight_g}g | 货值{c['rub']}R | 佣金率{int(c['commission_rate']*100)}%")
    CH_NAME = {"zto": "ZTO", "ogl": "OGL", "china_post": "ChinaPost陆运", "china_post_air": "ChinaPost空运"}
    for ch in ("zto", "ogl", "china_post", "china_post_air"):
        d = c["channels"][ch]
        if d.get("unavailable"):
            print(f"  {CH_NAME[ch]}: 不可用 —— {d['reason']}")
            continue
        print(f"  {CH_NAME[ch]}: {d['group']:16} 承运/运输¥{d['ship']:>7.2f} +2%¥{d['agent2pct']:>5.2f} +0.33%¥{d['cross033']:>5.2f} = 物流¥{d['logistics']:>7.2f} | 佣金¥{c['commission']:>7.2f} | 总成本¥{d['total_cost']:>7.2f} | 利润¥{d['profit']:>8.2f} | 利润率{d['margin']:>5.1f}%")
    print(f"  ✅ 推荐物流: {CH_NAME.get(c['best_channel'], c['best_channel'])} (利润¥{c['best_profit']:.2f}, 利润率{c['best_margin']:.1f}%)")
    if channel != "all":
        tgt = recommend_price(name, cost, weight_g, rate, category, custom_commission, channel, target_margin)
        cur = c["channels"][channel]
        flag = "已达标" if cur["margin"] >= target_margin * 100 else f"未达标(差{target_margin*100-cur['margin']:.1f}pp)"
        print(f"  🎯 目标利润率{int(target_margin*100)}%: 当前{cur['margin']:.1f}%({flag}) | 建议售价≥¥{tgt} (走{CH_NAME.get(c['best_channel'], c['best_channel'])})")
    print()


def main():
    p = argparse.ArgumentParser(description="Ozon 利润计算器")
    p.add_argument("--price", type=float, help="售价(CNY)")
    p.add_argument("--cost", type=float, help="进货成本(CNY)")
    p.add_argument("--weight", type=float, help="单件重量(g)")
    p.add_argument("--file", help="JSON 批量文件路径")
    p.add_argument("--rate", type=float, default=12.7154, help="汇率 1CNY=?RUB")
    p.add_argument("--commission", type=float, default=0.17, help="佣金率(仅 --category other 时使用)")
    p.add_argument("--category", default="car", choices=["car", "other"])
    p.add_argument("--target-margin", type=float, default=0.10, help="目标利润率")
    p.add_argument("--channel", default="all", choices=["all", "zto", "ogl", "china_post", "china_post_air"])
    p.add_argument("--json", action="store_true", help="JSON 输出")
    a = p.parse_args()

    rate, category, comm, tgt, ch = a.rate, a.category, a.commission, a.target_margin, a.channel

    if a.file:
        with open(a.file, "r", encoding="utf-8-sig") as f:  # 兼容 UTF-8 BOM
            goods = json.load(f)
    elif a.price is not None and a.cost is not None and a.weight is not None:
        goods = [{"name": "商品", "price": a.price, "cost": a.cost, "weight": a.weight}]
    else:
        print("需要 --price --cost --weight, 或 --file <json>")
        sys.exit(1)

    if a.json:
        out = []
        for g in goods:
            out.append(calc_one(g["name"], g["price"], g["cost"], g["weight"],
                                rate, category, comm))
            if ch != "all":
                out[-1]["recommended_price"] = recommend_price(
                    g["name"], g["cost"], g["weight"], rate, category, comm, ch, tgt)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    for g in goods:
        print_human(g["name"], g["price"], g["cost"], g["weight"], rate, category,
                    comm, ch, tgt, None)


if __name__ == "__main__":
    main()
