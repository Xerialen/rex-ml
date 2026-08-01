"""Vet candidate runs for the audit pairs with the pipeline's own vet() — no new thresholds."""
import json, sys
sys.path.insert(0, "/home/benjamin-adm/rex-ml")
from pipeline.human_paths import _con, fetch_paths, vet

runs = json.load(open("/tmp/claude-1001/-home-benjamin-adm-rex-ml/003dd697-8855-417d-9d80-53960851ebcf/scratchpad/vet_runs.json"))
con = _con()
con.execute("SET threads TO 16"); con.execute("SET memory_limit='60GB'")
by_run = fetch_paths(con, runs)

res = {}
for r in runs:
    key = (r["demo_key"], r["slot"], r["start_ms"])
    samples = by_run.get(key, [])
    ok, reason, stats = vet(samples, r["duration_s"])
    pair = f"{r['from']}->{r['to']}"
    d = res.setdefault(pair, {"cand": 0, "ok": 0, "reasons": {}, "ok_durations": []})
    d["cand"] += 1
    if ok:
        d["ok"] += 1
        d["ok_durations"].append(round(r["duration_s"], 2))
    else:
        d["reasons"][reason] = d["reasons"].get(reason, 0) + 1

for pair, d in sorted(res.items()):
    durs = sorted(d.pop("ok_durations"))
    d["ok_fastest_s"] = durs[0] if durs else None
    d["ok_median_s"] = durs[len(durs)//2] if durs else None
    d["ok_durations"] = durs[:30]
    print(pair, d["cand"], "cand,", d["ok"], "ok,", d["reasons"], "fastest", d["ok_fastest_s"])
json.dump(res, open("/tmp/claude-1001/-home-benjamin-adm-rex-ml/003dd697-8855-417d-9d80-53960851ebcf/scratchpad/vet_results.json","w"), indent=1)
