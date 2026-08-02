"""Gate-hopp (ägarbeslut 2026-08-01 ~16:00): mognadsstege per kritiskt trickhopp.

Ägarens kriterium — bottarna ska KUNNA dessa i sim innan MVD-tester:
  * ring↔quad över hexagonens BÅDA sidoledger — 4 hopp (NV/SO × båda riktningar),
    utan att ramla ner i MH-gropen (gropgolv -192; plattformar z=56),
  * RA-tagningen: uppklättring till item_armorInv (256,-704,304),
  * SNG-mega: hoppnavigering fram till megan (-720,80,160).
  (rjump pent/lift→window: uppskjuten av ägaren, kräver V3.)

Mognadsstegen (ägarens tre steg + nolla; nivå 3-tröskeln satt av ägaren
2026-08-01 ~17:05 till 90 % efter analystens mätning att eliten når 8-44 %
genom samma detektor — 100 % vore omätbart strängt även för botten):
  0 = inga försök; 1 = försöker (uppvisad medvetenhet om hoppet som genväg);
  2 = lyckas ibland (≥1 lyckat, men <5 försök eller <90 %);
  3 = ≥5 försök och ≥90 % lyckade.

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
# Analyst-korrigeringar (evidence/analyst_jumpgate_review.md, 2026-08-01):
# v1-detektorn underkändes — plattformsregionen utan z-band gjorde korridor-
# passager på golvet (z=56 exakt) till "försök", och grop-cirkulationen
# quad→MH→ring-nedre till "ramla". Korrigerat:
PLAT_ZBAND = (40.0, 130.0)            # plattformsNIVÅN, inte volymen över gropen
PROGRESS_D = 350.0                    # försök kräver närmande: d(dst) < 350 någon gång
SIDE_DEADZONE = 100.0                 # |perp| < 100 u räknas inte i sidoklassningen
# v5 (analyst-review 5, 2026-08-02, underkände ledgeprobens "quad→ring SO"):
# ett AXIALT gaphopp rakt ut i gropen fick SO-etikett av 2 luftburna sampel
# 0.8 u utanför dödzonen (side_acc 201; människors misslyckade SO-korsningar:
# min 205, median 12 468 över 472 event). Korrigeringar:
SIDE_LEDGE_MAX = 300.0                # ledgebandet: 100 < |perp| < 300 (voxelmätt)
# v5.1 (analystens villkorade förhandsgodkännande, evidence/analyst_v5_validation.md):
# in-band-progression 350 var geometriskt onåbar för mittgropsfall (gapmitten
# d=392, källranden 524) — tappade 34 % genuina misslyckade korsningar. 450 ger
# 97 % misslyckad-retention, 646/646 lyckade, 0 grazers.
PROGRESS_D_BAND = 450.0               # in-band-progression (rå axial behåller 350)
# Sidomassan tidsnormaliseras (u·s) — råsumman är dt-beroende (26 ms-botdata
# summerar 2x per tidsenhet mot 51 ms-demon). Humangap 12.0-15.4 u·s;
# behållna in-band-korsningar: min 301.8 rå @ deras dt; grazers max 234.6.
SIDE_MIN_MASS_US = 14.0               # |side_acc|·dt >= 14 u·s för sidoetikett
SAMPLE_DT = 0.026                     # botdumparnas sampelperiod (var 2:e tick @77 Hz)
# ledgenärvaro/progression/sidosignal räknas ENBART i sampel på plattformsnivån
# (z i PLAT_ZBAND) — progression intjänad i fritt fall under bandet räknas inte.
# Axiala gropkorsningar (utan ledgekvalificering) bokförs separat, ej som gate.
LEDGE_Z = -20.0                       # ledgenivå: över detta ute vid sidorna
HEX_R = 800.0                         # lokalitet kring gropen
MAX_TRANSIT_PTS = int(4.0 / 0.026)    # 4 s

RA = np.array([256.0, -704.0, 304.0])
MEGA_SNG = np.array([-720.0, 80.0, 160.0])
PICKUP_2D = 60.0
# dz-fönster (−32,+80): 88 % av 4 000 mänskliga RA-pickups inom boxen; dz p50
# +24, max +79.8 = QW:s touch-tak (analyst-mätt)
PICKUP_DZ_LO = -32.0
PICKUP_DZ_HI = 80.0
CLIMB_GAIN = 80.0                     # försök = klättring påbörjad: z_entry+80 nådd
# re-review-fix (analyst): klättring i intervallet räcker inte — ep29 klättrade
# trappan MOT TELE (d till RA ökade 157→299 under höjdvinsten). Försök kräver
# närmande: d2_min < 120 (mänskliga RA-pickups har d2 p99 = 61.7)
APPROACH_MIN = 120.0
# review 4-fix (analyst 2026-08-02): klättringsvillkorets sample måste vara
# STÖTT (grundat), inte luftburet mitt i en hoppbåge — annars räknas kedjade
# bunnyhops mot vägg som "klättring" (underkända mega-claimet @5.3G).
GROUND_DZ = 0.5                       # z-stabilitet ±0.5 u ...
GROUND_RUN = 3                        # ... över ≥3 konsekutiva sampel
# ... RÄCKER INTE ensamt: en hoppbåges APEX är kvasi-stabil (dz 0.4/0.1 vid
# 26 ms-sampling) men behåller gravitationens andradifferens ≈ −0.54 u/sampel².
# Grundat kräver därför även PLATT kurvatur (gravitationsfit-negation,
# analystens alternativ i review 4): |d²z| ≤ GROUND_D2Z.
GROUND_D2Z = 0.2

_AXIS = (QUAD - RING)[:2]


def _d2(p, c):
    return float(np.hypot(p[0] - c[0], p[1] - c[1]))


def _side(p) -> float:
    """Signerat vinkelrätt avstånd (u) från ring→quad-axeln: >0 = NV, <0 = SO.
    Punkter inom SIDE_DEADZONE från axeln exkluderas av anroparen (brus)."""
    v = np.array([p[0], p[1]]) - RING[:2]
    return float((_AXIS[0] * v[1] - _AXIS[1] * v[0]) / np.hypot(*_AXIS))


def _plat(p):
    """Plattformsregion = 2D-radie OCH plattformsnivån (z-band 40-130).
    Utan z-bandet räknades gropcirkulation under plattformarna som besök."""
    if not (PLAT_ZBAND[0] < p[2] < PLAT_ZBAND[1]):
        return None
    if _d2(p, RING) < PLAT_R:
        return "ring"
    if _d2(p, QUAD) < PLAT_R:
        return "quad"
    return None


def _ring_quad_events(path: np.ndarray, dt: float = SAMPLE_DT) -> list[dict]:
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
        progressed = False               # d(dst) < PROGRESS_D i ledgebandet (v5)
        raw_progressed = False           # d(dst) < PROGRESS_D var som helst (axial)
        side_acc = 0.0
        dst_c = QUAD if cur == "ring" else RING
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
                if _d2(q, dst_c) < PROGRESS_D:
                    raw_progressed = True
                # v5: ledgenärvaro/sidosignal/progression enbart på plattforms-
                # nivån — luftburna sampel under bandet (fritt fall i gropen)
                # kvalificerar inte ett sidogate-försök.
                if PLAT_ZBAND[0] < q[2] < PLAT_ZBAND[1]:
                    s = _side(q)
                    if SIDE_DEADZONE < abs(s) < SIDE_LEDGE_MAX:
                        onto_ledge = True
                    if abs(s) > SIDE_DEADZONE:
                        side_acc += s
                    if _d2(q, dst_c) < PROGRESS_D_BAND:
                        progressed = True
            if qp == cur:
                outcome = "retreat"
                break
            if qp is not None and qp != cur:
                outcome = "lyckat"
                break
            j += 1
        if outcome is None:
            outcome = "lämnade"              # timeout utan att nå fram
        if outcome == "lyckat":
            progressed = progressed or onto_ledge   # framme via ledgen ⇒ progression
            raw_progressed = True
        side_ok = abs(side_acc) * dt >= SIDE_MIN_MASS_US   # tidsnorm. massa (v5.1)
        if onto_ledge and progressed and side_ok \
                and outcome in ("lyckat", "ramla", "retreat"):
            dst = "quad" if cur == "ring" else "ring"
            side = "NV" if side_acc > 0 else "SO"
            events.append({"hopp": f"{cur}→{dst} {side}", "utfall": outcome})
        elif (raw_progressed or progressed) and outcome in ("lyckat", "ramla", "retreat"):
            # axial/okvalificerad gropkorsning — spåras separat (analyst-review 5:
            # "första uppvisade gropkorsningsintentionen", men INTE ett sidogate-
            # försök). Räknas aldrig mot mognadsstegen.
            dst = "quad" if cur == "ring" else "ring"
            events.append({"hopp": f"axial {cur}→{dst}", "utfall": outcome})
        cur = _plat(path[j]) if j < len(path) else None
        t0 = j
        i = j + 1
    return events


def _grounded(path: np.ndarray) -> np.ndarray:
    """Stödd/grundad per sample: z-stabil (±GROUND_DZ) mot BÅDA grannsamplen
    OCH platt kurvatur (|d²z| ≤ GROUND_D2Z). Bågapexen klarar dz-testet
    (dz 0.4/0.1 vid 26 ms) men inte kurvaturen — gravitationen ger d²z ≈ −0.54
    även i apex (verifierat på underkända mega-claimets sampel 2282: −0.5)."""
    z = path[:, 2]
    dz_ok = np.abs(np.diff(z)) <= GROUND_DZ
    g = np.zeros(len(path), dtype=bool)
    if len(path) > 2:
        flat = np.abs(z[2:] - 2.0 * z[1:-1] + z[:-2]) <= GROUND_D2Z
        g[1:-1] = dz_ok[:-1] & dz_ok[1:] & flat
    return g


def _item_events(path: np.ndarray, item: np.ndarray, approach_r: float,
                 low_pred) -> tuple[int, int]:
    """(försök, lyckade) för item-gates. Analyst-korrigerat (v1 räknade all
    korridortrafik som "försök", 95/96 RA-intervall var tele↔RA-nedre-passager):
    försök = besöksintervall som börjar lågt (low_pred) OCH där klättring
    PÅBÖRJAS (z stiger ≥ CLIMB_GAIN över intervallets entré-z);
    lyckat = pickupboxen nås (2D<60, dz i (−32,+80) = mänskligt touch-fönster)."""
    attempts = successes = 0
    inside = False
    low = climbed_near = suc = False
    z_entry = 0.0
    grounded = _grounded(path)
    for i, p in enumerate(path):
        d = _d2(p, item)
        if d < approach_r:
            if not inside:
                inside = True
                z_entry = p[2]
                low = bool(low_pred(p))      # bedöms vid ENTRÉN (analystnotering)
            # SAMTIDIGHET (analyst-review 3, 2026-08-01): klättring och närhet
            # måste hållas i SAMMA sample — disjunkta delsegment (golvcirkulation
            # med d2_min 70.9 på z=-16 + avsatsstuds z 67.8 på d2 126) gav falsk
            # positiv när villkoren ackumulerades separat.
            # GRUNDAT-KRAV (analyst-review 4, 2026-08-02, underkände mega-claimet
            # @5.3G): samtidighetssamplet måste dessutom vara STÖTT — ep6:s
            # "klättring" var två kedjade bunnyhop-bågar in i NO-hörnsväggen
            # (apex z 67.8 luftburet; max stödd z i intervallet = entré+0).
            # Människornas nerifrån-väg ger stödda platåer på entré+104..+136,
            # så grundat +80 behåller 21/24 mänskliga positiva (analyst-mätt).
            if p[2] >= z_entry + CLIMB_GAIN and d < APPROACH_MIN and grounded[i]:
                climbed_near = True
            if d < PICKUP_2D and \
                    PICKUP_DZ_LO < p[2] - item[2] < PICKUP_DZ_HI:
                suc = True
        elif inside:
            if low and climbed_near:
                attempts += 1
                successes += int(suc)
            inside, low, climbed_near, suc = False, False, False, False
    if inside and low and climbed_near:
        attempts += 1
        successes += int(suc)
    return attempts, successes


def _level(attempts: int, successes: int) -> int:
    if attempts == 0:
        return 0
    if successes == 0:
        return 1
    if attempts >= 5 and successes / attempts >= 0.90:
        return 3
    return 2


def analyze(dump: dict, dt: float | None = None) -> dict:
    gates: dict[str, dict] = {}
    dt = dt if dt is not None else float(dump.get("dt", SAMPLE_DT))
    rq = {f"{a}→{b} {s}": {"försök": 0, "lyckade": 0, "ramla": 0, "retreat": 0}
          for a, b in (("ring", "quad"), ("quad", "ring")) for s in ("NV", "SO")}
    axial = {"försök": 0, "lyckade": 0, "ramla": 0, "retreat": 0}
    ra_att = ra_suc = mega_att = mega_suc = 0
    for ep in dump["episodes"]:
        path = np.asarray(ep["path"], dtype=float)
        for ev in _ring_quad_events(path, dt=dt):
            g = axial if ev["hopp"].startswith("axial") else rq[ev["hopp"]]
            g["försök"] += 1
            g["lyckade"] += int(ev["utfall"] == "lyckat")
            g["ramla"] += int(ev["utfall"] == "ramla")
            g["retreat"] += int(ev["utfall"] == "retreat")
        a, s = _item_events(path, RA, 300.0, lambda p: p[2] < 150.0)
        ra_att += a; ra_suc += s
        a, s = _item_events(path, MEGA_SNG, 300.0, lambda p: p[2] < 100.0)
        mega_att += a; mega_suc += s
    for name, g in rq.items():
        gates[name] = {**g, "nivå": _level(g["försök"], g["lyckade"])}
    gates["RA-tagningen"] = {"försök": ra_att, "lyckade": ra_suc,
                             "nivå": _level(ra_att, ra_suc)}
    gates["SNG-mega"] = {"försök": mega_att, "lyckade": mega_suc,
                          "nivå": _level(mega_att, mega_suc)}
    return {"episodes": len(dump["episodes"]), "gates": gates,
            "axiala_gropkorsningar": axial,   # informationsspår, EJ gate (v5)
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
