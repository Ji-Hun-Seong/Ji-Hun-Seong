import json, os, sys, time
sys.path.insert(0, "toss-bot/chartpage")
import data_sources as ds, stock_info as si
os.makedirs("out", exist_ok=True)
for q in ["삼성전자", "코웨이", "세방", "AAPL", "UBER"]:
    it = ds.search(q, 1)[0]
    t = time.time()
    try:
        r = si.detail(it)
        json.dump(r, open(f"out/{it['code']}.json", "w"), ensure_ascii=False)
        print(q, it, "OK", round(time.time() - t, 1), r["errors"])
        for s in r["signals"]:
            print(f"  [{s['cat']}] {s['title']}: {s['value']} ({s['tone']}) {s['detail']}")
    except Exception as e:
        import traceback; traceback.print_exc()
