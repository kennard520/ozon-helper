"""拉遮阳网详细 offer，按代发友好度+尺寸+供应商给选品参考。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ozon-scraper"))
from ozon_scraper.alibaba import fetch_search_html, parse_alibaba_html  # noqa: E402

OUT = Path(__file__).resolve().parent / "data" / "shadenet_offers.json"

allrows = []
TERMS = sys.argv[1:] or ["遮阳网 庭院 包边 打孔", "遮阳网 成品 带孔 花园"]
for kw in TERMS:
    print(f"\n############ 搜索: {kw} ############", flush=True)
    html = fetch_search_html(kw, headless=True, timeout_ms=35_000)
    offers = parse_alibaba_html(html, limit=30)
    for o in offers:
        allrows.append(o.to_dict())
        moq = o.min_order
        flag = "✅代发" if (moq is not None and moq <= 2) else (f"MOQ{moq}" if moq else "MOQ?")
        print(f"  ¥{o.price_cny_min}~{o.price_cny_max} {flag} 年{o.supplier_years or '?'} 销{o.sold or '-'} | {(o.title or '')[:46]}", flush=True)

OUT.write_text(json.dumps(allrows, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n[+] 存 {len(allrows)} -> {OUT}", flush=True)
