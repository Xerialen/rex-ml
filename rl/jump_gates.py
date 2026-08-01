"""Gate-hopp (ägarbeslut 2026-08-01 ~16:00): mognadsstege per kritiskt trickhopp.

Ägarens kriterium — bottarna ska KUNNA dessa i sim innan MVD-tester:
  * ring↔quad över hexagonens BÅDA sidoledger — 4 hopp (NV/SO × båda riktningar),
    utan att ramla ner i MH-gropen (gropgolv -192; plattformar z=56),
  * RA-tagningen: uppklättring till item_armorInv (256,-704,304),
  * SNG-mega: hoppnavigering fram till megan (-720,80,160).
  (rjump pent/lift→window: uppskjuten av ägaren, kräver V3.)

Mognadsstegen (ägarens tre steg + nolla):
  0 = inga försök; 1 = försöker (uppvisad medvetenhet om hoppet som genväg);
  2 = lyckas ibland (≥1 lyckat, men <5 försök eller <100 %);
  3 = ≥5 försök och 100 % lyckade.

Mäter på dump_trajectories-JSON (path = var 2:e tick ⇒ 26 ms mellan punkter).
"""
from __future__ import annotations

import argparse
import json

import numpy as np

RING = np.array([240.0, -32.0, 56.0])
QUAD = np.array([952.0, 296.0, 56.0])
PIT_2D = np.array([564.0, -48.0])     # MH-gropen mellan plattformarna
PIT_Z = -100.0                        # under detta = nere i gropen ("ramla ner")
PLAT_R = 260.0                        # 2D-radie plattformsregion
LEDGE_Z = -20.0                       # ledgenivå: över detta ute vid sidorna
HEX_R = 800.0                         # lokalitet kring gropen
MAX_TRANSIT_PTS = int(4.0 / 0.026)    # 4 s

RA = np.array([256.0, -704.0, 304.0])
MEGA_SNG = np.array([-720.0, 80.0, 160.0])
PICKUP_2D = 60.0
PICKUP_DZ = 56.0

_AXIS = (QUAD - RING)[:2]


def _d2(p, c):
    return float(np.hypot(p[0] - c[0], p[1] - c[1]))


def _side(p) -> float:
    """Tecken på kryssprodukten mot ring→quad-axeln: >0 = NV-ledgen, <0 = SO."""
    v = np.array([p[0], p[1]]) - RING[:2]
    return float(_AXIS[0] * v[1] - _AXIS[1] * v[0])


def _plat(p):
    if _d2(p, RING) < PLAT_R:
        return "ring"
    if _d2(p, QUAD) < PLAT_R:
        return "quad"
    return None


def _ring_quad_events(path: np.ndarray) -> list[dict]:
    """Transitförsök mellan plattformarna via sidoledgerna."""
    events = []
    cur = _plat(path[0])
    t0 = 0
    i = 1
    while i < len(path):
        p = path[i]
        plat = _plat(p)
        if cur is None:
            cur, t0 = plat, i
            i += 1
            continue
        if plat == cur:
            t0 = i
            i += 1
            continue
        # lämnat cur-plattformen: följ kandidattransiten
        seg = [path[t0]]
        outcome = None
        onto_ledge = False
        side_acc = 0.0
        j = i
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            seg.append(q)
            if _d2(q, PIT_2D) > HEX_R:
                outcome = "lämnade"          # drog någon annanstans — inget försök
                break
            if q[2] <= PIT_Z:
                outcome = "ramla"            # nere i gropen
                break
            qp = _plat(q)
            if qp is None and q[2] > LEDGE_Z:
                onto_ledge = True
                side_acc += _side(q)
            if qp == cur:
                outcome = "retreat"
                break
            if qp is not None and qp != cur:
                outcome = "lyckat"
                break
            j += 1
        if outcome is None:
            outcome = "lämnade"              # timeout utan att nå fram
        if onto_ledge and outcome in ("lyckat", "ramla", "retreat"):
            dst = "quad" if cur == "ring" else "ring"
            events.append({
                "hopp": f"{cur}→{dst} {'NV' if side_acc > 0 else 'SO'}",
                "utfall": outcome,
            })
        cur = _plat(path[j]) if j < len(path) else None
        t0 = j
        i = j + 1
    return events


def _item_events(path: np.ndarray, item: np.ndarray, approach_r: float,
                 attempt_pred) -> tuple[int, int]:
    """(försök, lyckade) för item-gates: besöksintervall inom approach_r;
    försök om attempt_pred uppfylls i intervallet, lyckat om pickup nås."""
    attempts = successes = 0
    inside = False
    att = suc = False
    for p in path:
        if _d2(p, item) < approach_r:
            inside = True
            if attempt_pred(p):
                att = True
            if _d2(p, item) < PICKUP_2D and abs(p[2] - item[2]) < PICKUP_DZ:
                suc = True
        elif inside:
            if att:
                attempts += 1
                successes += int(suc)
            inside, att, suc = False, False, False
    if inside and att:
        attempts += 1
        successes += int(suc)
    return attempts, successes


def _level(attempts: int, successes: int) -> int:
    if attempts == 0:
        return 0
    if successes == 0:
        return 1
    if attempts >= 5 and successes == attempts:
        return 3
    return 2


def analyze(dump: dict) -> dict:
    gates: dict[str, dict] = {}
    rq = {f"{a}→{b} {s}": {"försök": 0, "lyckade": 0, "ramla": 0, "retreat": 0}
          for a, b in (("ring", "quad"), ("quad", "ring")) for s in ("NV", "SO")}
    ra_att = ra_suc = mega_att = mega_suc = 0
    for ep in dump["episodes"]:
        path = np.asarray(ep["path"], dtype=float)
        for ev in _ring_quad_events(path):
            g = rq[ev["hopp"]]
            g["försök"] += 1
            g["lyckade"] += int(ev["utfall"] == "lyckat")
            g["ramla"] += int(ev["utfall"] == "ramla")
            g["retreat"] += int(ev["utfall"] == "retreat")
        a, s = _item_events(path, RA, 300.0, lambda p: p[2] < 150.0)
        ra_att += a; ra_suc += s
        a, s = _item_events(path, MEGA_SNG, 300.0, lambda p: p[2] > 100.0)
        mega_att += a; mega_suc += s
    for name, g in rq.items():
        gates[name] = {**g, "nivå": _level(g["försök"], g["lyckade"])}
    gates["RA-tagningen"] = {"försök": ra_att, "lyckade": ra_suc,
                             "nivå": _level(ra_att, ra_suc)}
    gates["SNG-mega"] = {"försök": mega_att, "lyckade": mega_suc,
                          "nivå": _level(mega_att, mega_suc)}
    return {"episodes": len(dump["episodes"]), "gates": gates,
            "min_nivå": min(g["nivå"] for g in gates.values())}


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
