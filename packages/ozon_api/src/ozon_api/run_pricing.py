"""把 8 个当季绿区选品的 1688 成本 + Ozon 售价跑 /price calc，算毛利。"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CALC = REPO / ".claude" / "skills" / "price" / "calc.py"
RUB = 0.0927

# zh, cost_cny(1688中位), weight_g, category, ozon_avgCaRub, window
PICKS = [
    ("门用防蚊纱门", 25.9, 200, "家居装饰", 740, "夏季"),
    ("卷帘窗帘", 60, 500, "家居装饰", 1427, "四季"),
    ("数字油画diy", 14.7, 400, "家居装饰", 750, "四季"),
    ("遮阳网", 13.5, 300, "通用", 1151, "夏季"),
    ("爬藤网", 8.1, 200, "通用", 367, "夏季"),
    ("门垫地垫", 29.0, 600, "家居装饰", 718, "四季"),
    ("驱蚊手环", 9.9, 30, "通用", 278, "夏季"),
    ("浴室置物架", 40.6, 500, "收纳整理", 1272, "四季"),
]


def run(cost, wt, cat, mp):
    r = subprocess.run(
        [sys.executable, str(CALC), "--cost", str(cost), "--weight", str(wt),
         "--category", cat, "--platform", "ozon", "--fulfillment", "fbp",
         "--market-price", str(mp), "--no-fetch-fx", "--output", "json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    d = json.loads(r.stdout)
    return d["results"][cat]["ozon"]


print(f"{'窗口':<4}{'品':<14}{'成本¥':>7}{'Ozon售价¥':>10}{'保本¥':>8}{'推荐¥':>8}{'每单赚¥':>9}{'毛利率':>7} 判定")
out = []
for zh, cost, wt, cat, rub, win in PICKS:
    mp = round(rub * RUB, 1)
    try:
        r = run(cost, wt, cat, mp)
    except Exception as e:  # noqa: BLE001
        print(f"{win:<4}{zh:<14} ERR {e}")
        continue
    be = r.get("breakeven_cny")
    tg = r.get("target_cny")
    pf = r.get("target_profit_abs")
    margin = r.get("target_margin")
    keys_dump = {k: v for k, v in r.items() if not isinstance(v, (dict, list))}
    verdict = "✅做得" if (tg and mp >= tg) else ("⚠️勉强" if (be and mp >= be) else "❌做不了")
    print(f"{win:<4}{zh:<14}{cost:>7}{mp:>10}"
          f"{(be if be is not None else '-'):>8}{(tg if tg is not None else '-'):>8}"
          f"{(pf if pf is not None else '-'):>9}{(margin if margin is not None else '-'):>7} {verdict}")
    out.append({"zh": zh, "window": win, "cost": cost, "ozon_price_cny": mp,
                "breakeven": be, "target": tg, "profit": pf, "verdict": verdict,
                "_all": keys_dump})

(Path(__file__).resolve().parent / "data" / "pricing_result.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

# 第一个的全部可用字段，便于核对口径
if out:
    print("\n[字段口径]", list(out[0]["_all"].keys()))
