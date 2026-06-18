# -*- coding: utf-8 -*-
"""全量采集 JOINSUN 店铺 80 个商品 → 草稿。
- 复用 app_service.collect（带登录态 .auth/1688_profile、auto 类目、图/视频本地化）
- 断点续抓：按 1688 offer id 跳过已采（有标题的）
- 分批降速 + 连续失败自停（风控）
- 进度写 _shop_batch_progress.json，可中途查
"""
import sys, json, re, time
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app_service import App

IDS = json.loads(Path('tools/ozon-listing-webui/_shop_offers.json').read_text(encoding='utf-8'))
PROG = Path('tools/ozon-listing-webui/_shop_batch_progress.json')
BATCH = 16          # 每批 url 数（一次开一个登录态浏览器采这批）
SLEEP_BETWEEN = 10  # 批间降速秒

svc = App()

# 断点续：库里已存在且有标题(非空壳)的 offer id 跳过
done_ids = set()
try:
    for d in svc.store.list_drafts():
        m = re.search(r'/offer/(\d+)', str(d.get('source_url') or ''))
        if m and (d.get('source_title') or '').strip():
            done_ids.add(m.group(1))
except Exception as e:
    print('读已有草稿失败(忽略):', e, flush=True)

todo = [i for i in IDS if i not in done_ids]
print(f"全部 {len(IDS)} | 已采 {len(done_ids)} | 待采 {len(todo)}", flush=True)
if not todo:
    print("=== 全部已采,无需再跑 ===", flush=True)
    sys.exit(0)

ok = fail = 0
consec_fail = 0
batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
for bi, batch in enumerate(batches, 1):
    urls = "\n".join(f"https://detail.1688.com/offer/{i}.html" for i in batch)
    try:
        res = svc.collect({"urls": urls, "source_platform": "1688"})
    except Exception as e:
        print(f"批 {bi}/{len(batches)} collect 异常: {e}", flush=True)
        consec_fail += 1
        if consec_fail >= 2:
            print("⚠ 连续 2 批异常,停。冷却后重跑可断点续。", flush=True)
            break
        time.sleep(SLEEP_BETWEEN)
        continue
    errs = [e for e in (res.get('errors') or []) if f"/offer/" in str(e.get('url') or '')]
    err_ids = {re.search(r'/offer/(\d+)', str(e.get('url'))).group(1)
               for e in errs if re.search(r'/offer/(\d+)', str(e.get('url') or ''))}
    err_ids &= set(batch)
    b_ok = len(batch) - len(err_ids)
    b_fail = len(err_ids)
    ok += b_ok
    fail += b_fail
    blocked = any(('反爬' in str(e.get('error', '')) or '登录' in str(e.get('error', '')))
                  for e in errs)
    consec_fail = consec_fail + 1 if b_ok == 0 else 0
    done = sum(len(b) for b in batches[:bi])
    print(f"批 {bi}/{len(batches)}: 本批 +{b_ok} / 失败 {b_fail} | 累计 成功 {ok} 失败 {fail} | 进度 {done}/{len(todo)}", flush=True)
    for e in errs[:3]:
        print("   err:", e.get('url'), str(e.get('error'))[:70], flush=True)
    PROG.write_text(json.dumps(
        {"done": done, "total": len(todo), "ok": ok, "fail": fail,
         "batch": bi, "batches": len(batches)}, ensure_ascii=False), encoding='utf-8')
    if consec_fail >= 2 and blocked:
        print("⚠ 连续 2 批全失败且疑似风控,停。冷却后重跑可断点续。", flush=True)
        break
    if bi < len(batches):
        time.sleep(SLEEP_BETWEEN)

print(f"=== 完成:{ok} 成功 / {fail} 失败 (待采过 {len(todo)}) ===", flush=True)
