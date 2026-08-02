"""Ledande indikatorer för gate-hoppen (ägardirektiv 2026-08-02: "utvärdera
proaktivt om vi kommer närmare att bottarna börjar göra hexagon- och andra
trickhopp"). Detektorn i jump_gates.py är binär (försök/ej) — den här mäter
FÖRSTADIERNA, så att vi ser rörelse mot hoppen innan första försöket:

hexagon (ring↔quad):
  * plattformstid: andel samples på ring-/quad-plattformsnivån,
  * ledgetid: andel samples ute på sidoledgerna (hexregion, av plattform,
    z över ledgenivå, utanför sidodeadzonen) — direkta förstadiet till transit,
  * närmsta-annalkande: per plattformsbesök min 2D-avstånd till MOTSATT
    plattform medan boten är ute på ledgenivå (attempt kräver <350),
  * gropfall från ledge: ledgevistelser som slutar i gropen (medvetenhetskostnad).

RA / SNG-mega:
  * regiontid (d2<300), besök som börjar lågt, max z-vinst över entré-z per
    besök (attempt kräver +80), min d2 under höjdvinst (attempt kräver <120).

Samma konstanter som jump_gates ⇒ måtten är förstadier till exakt samma
detektor som analysten godkänt. Körs på dump_trajectories-JSON.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from rl.jump_gates import (APPROACH_MIN, CLIMB_GAIN, HEX_R, LEDGE_Z, MEGA_SNG,
                           PIT_2D, PIT_Z, RA, SIDE_DEADZONE, _d2, _plat, _side)

RING_C = np.array([240.0, -32.0])
QUAD_C = np.array([952.0, 296.0])


def _hex_indicators(path: np.ndarray) -> dict:
    n = len(path)
    plat_pts = ledge_pts = 0
    approach_mins: list[float] = []      # min d(motsatt) per ledgevistelse
    ledge_falls = 0
    cur_min = None
    cur_src = None
    for p in path:
        plat = _plat(p)
        if plat is not None:
            plat_pts += 1
            if cur_min is not None:
                approach_mins.append(cur_min)
                cur_min = None
            cur_src = plat
            continue
        on_ledge = (_d2(p, PIT_2D) < HEX_R and p[2] > LEDGE_Z
                    and abs(_side(p)) > SIDE_DEADZONE and p[2] < 130.0)
        if on_ledge and cur_src is not None:
            ledge_pts += 1
            dst = QUAD_C if cur_src == "ring" else RING_C
            d = _d2(p, dst)
            cur_min = d if cur_min is None else min(cur_min, d)
        elif cur_min is not None:
            if p[2] <= PIT_Z:
                ledge_falls += 1
            approach_mins.append(cur_min)
            cur_min = None
            if _d2(p, PIT_2D) > HEX_R:
                cur_src = None
    if cur_min is not None:
        approach_mins.append(cur_min)
    return {"n": n, "plat_pts": plat_pts, "ledge_pts": ledge_pts,
            "approach_mins": approach_mins, "ledge_falls": ledge_falls}


def _item_indicators(path: np.ndarray, item: np.ndarray, low_z: float) -> dict:
    region_pts = 0
    visits: list[dict] = []
    inside = False
    z_entry = 0.0
    low = False
    zgain_max = 0.0
    d2_min_elev = None                   # min d2 medan z >= entré+40 (halvvägs)
    for p in path:
        d = _d2(p, item)
        if d < 300.0:
            region_pts += 1
            if not inside:
                inside, z_entry = True, p[2]
                low = p[2] < low_z
                zgain_max, d2_min_elev = 0.0, None
            zgain_max = max(zgain_max, p[2] - z_entry)
            if p[2] >= z_entry + CLIMB_GAIN / 2:
                d2_min_elev = d if d2_min_elev is None else min(d2_min_elev, d)
        elif inside:
            visits.append({"low": low, "zgain": zgain_max, "d2min": d2_min_elev})
            inside = False
    if inside:
        visits.append({"low": low, "zgain": zgain_max, "d2min": d2_min_elev})
    return {"n": len(path), "region_pts": region_pts, "visits": visits}


def analyze(dump: dict) -> dict:
    tot = 0
    hexa = {"plat_pts": 0, "ledge_pts": 0, "approach_mins": [], "ledge_falls": 0}
    items = {"RA": {"region_pts": 0, "visits": []},
             "SNG-mega": {"region_pts": 0, "visits": []}}
    for ep in dump["episodes"]:
        path = np.asarray(ep["path"], dtype=float)
        tot += len(path)
        h = _hex_indicators(path)
        for k in ("plat_pts", "ledge_pts", "ledge_falls"):
            hexa[k] += h[k]
        hexa["approach_mins"] += h["approach_mins"]
        for name, (item, lz) in (("RA", (RA, 150.0)),
                                 ("SNG-mega", (MEGA_SNG, 100.0))):
            r = _item_indicators(path, item, lz)
            items[name]["region_pts"] += r["region_pts"]
            items[name]["visits"] += r["visits"]

    am = np.array(hexa["approach_mins"]) if hexa["approach_mins"] else None
    out = {
        "episodes": len(dump["episodes"]),
        "hexagon": {
            "plattformstid_pct": round(100 * hexa["plat_pts"] / tot, 2),
            "ledgetid_pct": round(100 * hexa["ledge_pts"] / tot, 2),
            "ledgevistelser": len(hexa["approach_mins"]),
            "ledgefall_i_grop": hexa["ledge_falls"],
            "annalkande_min_p50": round(float(np.median(am)), 1) if am is not None else None,
            "annalkande_min_best": round(float(am.min()), 1) if am is not None else None,
            "annalkande_under_350": int((am < 350.0).sum()) if am is not None else 0,
        },
    }
    for name, r in items.items():
        vs = r["visits"]
        lows = [v for v in vs if v["low"]]
        zg = np.array([v["zgain"] for v in lows]) if lows else None
        d2s = [v["d2min"] for v in lows if v["d2min"] is not None]
        out[name] = {
            "regiontid_pct": round(100 * r["region_pts"] / tot, 2),
            "besök_låga": len(lows),
            "zvinst_p50": round(float(np.median(zg)), 1) if zg is not None else None,
            "zvinst_max": round(float(zg.max()), 1) if zg is not None else None,
            "zvinst_over_40": int((zg >= CLIMB_GAIN / 2).sum()) if zg is not None else 0,
            "zvinst_over_80": int((zg >= CLIMB_GAIN).sum()) if zg is not None else 0,
            "d2min_elev_best": round(min(d2s), 1) if d2s else None,
            "d2min_krav": APPROACH_MIN,
        }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    res = analyze(json.load(open(args.dump)))
    txt = json.dumps(res, indent=1, ensure_ascii=False)
    if args.out:
        open(args.out, "w").write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
