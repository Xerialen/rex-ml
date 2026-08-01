import json, sys
sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import duckdb
from pipeline.human_paths import _con, fetch_paths, vet

IE = "/home/benjamin-adm/dm3-extract/store-dm3/item_events/**/*.parquet"
SP = "/home/benjamin-adm/dm3-extract/store-dm3/spawns/**/*.parquet"
con = _con(); con.execute("SET threads TO 16"); con.execute("SET memory_limit='60GB'")

# all ya->rl same-life runs (same semantics as pair_counts.py), no fastest-cap
sql = f"""
WITH ev AS (
  SELECT demo_key,
         CASE WHEN item_id='ya' AND abs(x-1232.0)<0.5 AND abs(y-(-904.0))<0.5 AND abs(z-(-48.0))<0.5 THEN 'ya'
              WHEN item_id='rl' AND abs(x-1520.0)<0.5 AND abs(y-496.0)<0.5 AND abs(z-(-112.0))<0.5 THEN 'rl' END AS node,
         event, t, taken_by_slot
  FROM read_parquet('{IE}', hive_partitioning=true, union_by_name=true)
  WHERE map='dm3' AND format='mvd' AND mode='4on4' AND event IN ('spawn','respawn','taken')
    AND item_id IN ('ya','rl')
), ev2 AS (SELECT * FROM ev WHERE node IS NOT NULL),
takes AS (
  SELECT demo_key, node, t, taken_by_slot AS slot,
         lag(t) OVER (PARTITION BY demo_key, node ORDER BY t) AS prev_take_t
  FROM ev2 WHERE event='taken' AND taken_by_slot IS NOT NULL
), pspawns AS (
  SELECT DISTINCT demo_key, slot, t FROM read_parquet('{SP}', hive_partitioning=true, union_by_name=true)
  WHERE map='dm3' AND format='mvd' AND mode='4on4'
), pairs AS (
  SELECT a.demo_key, a.slot, a.t AS t1, b.t AS t2, b.prev_take_t,
         row_number() OVER (PARTITION BY a.demo_key, a.slot, b.t ORDER BY a.t DESC) AS source_rank
  FROM takes a JOIN takes b ON b.demo_key=a.demo_key AND b.slot=a.slot
   AND b.t>a.t AND b.t-a.t<=15000 AND a.node='ya' AND b.node='rl'
), latest_src AS (SELECT * FROM pairs WHERE source_rank=1),
first_take AS (SELECT * FROM latest_src WHERE prev_take_t IS NULL OR prev_take_t<=t1),
active AS (
  SELECT p.* FROM first_take p
  WHERE (SELECT e.event FROM ev2 e WHERE e.demo_key=p.demo_key AND e.node='rl' AND e.t<=p.t1
         ORDER BY e.t DESC, CASE e.event WHEN 'taken' THEN 1 ELSE 0 END DESC LIMIT 1) IN ('spawn','respawn')
), same_life AS (
  SELECT p.* FROM active p
  WHERE NOT EXISTS (SELECT 1 FROM pspawns s WHERE s.demo_key=p.demo_key AND s.slot=p.slot
                    AND s.t>p.t1 AND s.t<=p.t2)
)
SELECT demo_key, slot, t1, t2, (t2-t1)/1000.0 FROM same_life ORDER BY t2-t1
"""
rows = con.execute(sql).fetchall()
runs = [dict(zip(["demo_key","slot","start_ms","end_ms","duration_s"], r)) for r in rows]
print("total ya->rl same-life runs:", len(runs))
by_run = fetch_paths(con, runs)
ok_durs, reasons = [], {}
for r in runs:
    samples = by_run.get((r["demo_key"], r["slot"], r["start_ms"]), [])
    ok, reason, stats = vet(samples, r["duration_s"])
    if ok: ok_durs.append(round(r["duration_s"],2))
    else: reasons[reason] = reasons.get(reason,0)+1
ok_durs.sort()
print("ok:", len(ok_durs), "reasons:", reasons)
print("fastest ok:", ok_durs[:10])
json.dump({"n": len(runs), "ok": len(ok_durs), "reasons": reasons, "ok_fastest": ok_durs[:30]},
          open("/tmp/claude-1001/-home-benjamin-adm-rex-ml/003dd697-8855-417d-9d80-53960851ebcf/scratchpad/ya_rl_full.json","w"))
