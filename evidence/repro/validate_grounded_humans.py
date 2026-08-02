"""Återvalidering (analyst, review 4-fixen): grundat-kravet i _item_events
mot mänskliga låg-entré-tagningar av SNG-megan och RA.

Metod: samma 400-pickups-sampel per item som i review 4 (hash-ordnat,
reproducerbart). För varje pickup extraheras (demo_key, slot)-trajektorian
[t-25 s, t+2 s], splittas på gap >150 ms, och körs genom patchade
_item_events (grundat-krav) respektive gamla logiken (grundat forcerat True).
Rapporterar retention av räknade låg-entré-försök och lyckanden.

Obs: mänsklig MVD-data är ~51 ms/sampel (uppmätt dt-mode 50-52 ms) mot
detektorns 26 ms-grid; gravitationens d²z är där ~2.1 u/sampel² — grundat-
separationen är alltså STARKARE på människodata än på botdumpar.

Kör:  ~/rex-ml/.venv/bin/python ~/rex-ml/evidence/repro/validate_grounded_humans.py
"""
import sys
from unittest import mock

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
from rl import jump_gates as jg  # noqa: E402

IE = "/home/benjamin-adm/dm3-extract/store-dm3/item_events/*/*/*/*.parquet"
P = "/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/*/*/*/*/*.parquet"
W = "format='mvd' and mode='4on4' and map='dm3'"

con = duckdb.connect()
con.execute("SET threads TO 14; SET memory_limit='20GB'")


def pickups(ix, iy, iz, n=400):
    return con.sql(f"""
     select demo_key, t, taken_by_slot
     from read_parquet('{IE}', hive_partitioning=1)
     where event='taken' and abs(x-({ix}))<40 and abs(y-({iy}))<40
       and abs(z-({iz}))<40
     order by hash(demo_key*13+t) limit {n}
    """).fetchall()


def run_item(path, item, low_z, grounded_on):
    if grounded_on:
        return jg._item_events(path, item, 300.0, lambda p: p[2] < low_z)
    with mock.patch.object(jg, "_grounded",
                           lambda p: np.ones(len(p), dtype=bool)):
        return jg._item_events(path, item, 300.0, lambda p: p[2] < low_z)


def validate(name, item, low_z):
    px = pickups(item[0], item[1], item[2])
    keys = sorted(set(p[0] for p in px))
    kl = ",".join(map(str, keys))
    rows = con.sql(f"""
     select demo_key, slot, t, x, y, z
     from read_parquet('{P}', hive_partitioning=1)
     where {W} and demo_key in ({kl})
     order by demo_key, slot, t
    """).fetchnumpy()
    dk, sl, t = rows["demo_key"], rows["slot"], rows["t"]
    xyz = np.stack([rows["x"], rows["y"], rows["z"]], 1).astype(float)
    import collections
    idx = collections.defaultdict(list)
    for i in range(len(dk)):
        idx[(dk[i], sl[i])].append(i)
    idx = {k: np.array(v) for k, v in idx.items()}

    stats = {"pickups": 0, "old_att": 0, "old_suc": 0,
             "new_att": 0, "new_suc": 0, "lost": []}
    for demo, tt, slot in px:
        ii = idx.get((demo, slot))
        if ii is None:
            continue
        win = ii[(t[ii] >= tt - 25000) & (t[ii] <= tt + 2000)]
        if len(win) < 20:
            continue
        # splitta på gap > 150 ms, kör per segment, summera
        tw = t[win]
        cuts = np.flatnonzero(np.diff(tw) > 150) + 1
        oa = os_ = na = ns = 0
        for a, b in zip(np.concatenate([[0], cuts]),
                        np.concatenate([cuts, [len(win)]])):
            if b - a < 10:
                continue
            path = xyz[win[a:b]]
            x1, y1 = run_item(path, item, low_z, grounded_on=False)
            x2, y2 = run_item(path, item, low_z, grounded_on=True)
            oa += x1; os_ += y1; na += x2; ns += y2
        stats["pickups"] += 1
        stats["old_att"] += oa; stats["old_suc"] += os_
        stats["new_att"] += na; stats["new_suc"] += ns
        if os_ > ns:
            stats["lost"].append((int(demo), int(slot), int(tt)))
    print(f"\n== {name} ==")
    print(f"pickup-fönster analyserade: {stats['pickups']}")
    print(f"GAMMAL logik: låg-entré-försök {stats['old_att']}, "
          f"varav lyckade {stats['old_suc']}")
    print(f"NY logik (grundat): låg-entré-försök {stats['new_att']}, "
          f"varav lyckade {stats['new_suc']}")
    if stats["old_suc"]:
        print(f"retention lyckade: {stats['new_suc']}/{stats['old_suc']} "
              f"= {stats['new_suc'] / stats['old_suc'] * 100:.0f} %")
    if stats["lost"]:
        print("tappade lyckanden (demo, slot, t):", stats["lost"][:10])
    return stats


validate("SNG-mega", jg.MEGA_SNG, 100.0)
validate("RA-tagningen", jg.RA, 150.0)
