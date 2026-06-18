import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CALC = REPO / ".claude" / "skills" / "price" / "calc.py"
RUB = 0.0927

# 尺寸, 1688成本¥(基础平板款估), 重量g, Ozon售价₽(该尺寸实测)
SIZES = [
    ("迷彩网 1.5×3м", 15, 300, 539),
    ("迷彩网 3×4м", 35, 600, 1204),
    ("迷彩网 3×6м", 50, 900, 1521),
    ("迷彩网 3×4м(3D树叶款)", 85, 700, 1521),
]
CAT = "家居装饰"

print(f"{'SKU':<22}{'成本¥':>6}{'Ozon售价¥':>9}{'保本¥':>7}{'推荐¥':>7}{'每单赚¥':>8} 判定")
for name, cost, wt, rub in SIZES:
    mp = round(rub * RUB, 1)
    r = subprocess.run(
        [sys.executable, str(CALC), "--cost", str(cost), "--weight", str(wt),
         "--category", CAT, "--platform", "ozon", "--fulfillment", "fbp",
         "--market-price", str(mp), "--no-fetch-fx", "--output", "json"],
        capture_output=True, text=True, encoding="utf-8")
    d = json.loads(r.stdout)["results"][CAT]["ozon"]
    be, tg, pf = d.get("breakeven_cny"), d.get("target_cny"), d.get("target_profit_abs")
    verdict = "✅做得" if (tg and mp >= tg) else ("⚠️勉强" if (be and mp >= be) else "❌做不了")
    print(f"{name:<22}{cost:>6}{mp:>9}{be:>7}{tg:>7}{pf:>8} {verdict}")
