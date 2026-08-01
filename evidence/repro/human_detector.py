"""Kör jump_gates-detektorns exakta logik på mänskliga 4on4-dm3-trajektorier."""
import sys
from collections import Counter

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml/rl")
import jump_gates as jg  # noqa: E402

N_DEMOS = int(sys.argv[1]) if len(sys.argv) > 1 else 60

con = duckdb.connect()
con.execute("SET threads TO 14; SET memory_limit='20GB'")
P = "/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/*/*/*/*/*.parquet"
W = "format='mvd' and mode='4on4' and map='dm3'"

keys = [r[0] for r in con.sql(
    f"select distinct demo_key from read_parquet('{P}', hive_partitioning=1) "
    f"where {W} order by hash(demo_key) limit {N_DEMOS}").fetchall()]
kl = ",".join(map(str, keys))
print(f"demos: {len(keys)}", flush=True)

rows = con.sql(f"""
 select demo_key, slot, t, x, y, z
 from read_parquet('{P}', hive_partitioning=1)
 where {W} and demo_key in ({kl})
   and sqrt((x-564)*(x-564)+(y+48)*(y+48)) < 1100
 order by demo_key, slot, t
""").fetchnumpy()
print(f"rows: {len(rows['t'])}", flush=True)

dk = rows["demo_key"]; sl = rows["slot"]; t = rows["t"]
xyz = np.stack([rows["x"], rows["y"], rows["z"]], axis=1).astype(float)

cnt = Counter()
succ_examples = []
# split per (demo,slot) och vid tidsgap > 100 ms; nedsampla till ~26 ms (var 2:a)
change = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)
                        | (np.diff(t) > 100)) + 1
starts = np.concatenate([[0], change, [len(dk)]])
nseg = 0
for a, b in zip(starts[:-1], starts[1:]):
    if b - a < 8:
        continue
    path = xyz[a:b:2]
    if len(path) < 4:
        continue
    nseg += 1
    for ev in jg._ring_quad_events(path):
        cnt[(ev["hopp"], ev["utfall"])] += 1
print(f"segment körda: {nseg}")
tot = Counter()
for (hopp, utfall), n in sorted(cnt.items()):
    print(f"{hopp:15s} {utfall:8s} {n}")
    tot[hopp] += n
print("\nper hopp (försök totalt):")
for hopp, n in sorted(tot.items()):
    ly = cnt[(hopp, "lyckat")]
    print(f"{hopp:15s} försök={n:5d} lyckade={ly:5d} ({ly/n*100:.0f} %)")
