"""Gate 2 zone classification for dm3: which 32u voxels count toward the >500 UPS
free-roam average, derived from BSP geometry + measured human speed distributions.

Stages (run as: .venv/bin/python -m pipeline.gate2_zones <stage>):
  stats     - duckdb pass over store-dm3 trajectory_samples (908 M rows): per-32u-voxel
              sample count + horizontal-speed p50/p95/p99/max via central difference,
              3-sample median filtered. Writes pipeline/out/gate2/voxel_stats.parquet.
  classify  - BSP leaf contents + entity volumes -> per-voxel class; connected-component
              clustering of constrained voxels -> named zones.
              Writes voxel_classes.npz + zone_map.parquet.
  zonestats - second duckdb pass joining zone_map -> EXACT sample-level per-zone/per-class
              speed percentiles (voxel-level aggregates cannot be recombined into
              sample-level quantiles). Writes zone_stats.parquet.
  report    - assembles evidence/gate2_zones.{json,md}.

Measurement choices (documented per the brief):
  * HORIZONTAL speed only: 16u stair position-steps produce phantom vz spikes up to
    ~1140 u/s; vertical velocity is excluded from the gate metric entirely.
  * Central difference over (t[i+1]-t[i-1]) per (demo_key, slot), both gaps required
    <= 200 ms and both 3D step distances <= 250 u (drops respawns, teleports, pauses,
    packet loss). The store has no run column; demo/slot partitions + the discontinuity
    filters ARE the run boundaries.
  * 3-sample median filter on the horizontal-speed sequence before any percentile,
    to kill residual single-sample spikes from MVD 0.125u position quantisation.
  * MVD samples carry no velocity columns (velocity_present=false), hence the
    finite differencing; QWD rows are treated identically for uniformity.
"""

from __future__ import annotations

import glob
import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REX = Path("/home/benjamin-adm/rex-ml")
BSP_PATH = Path("/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/dm3.bsp")
STORE = Path("/home/benjamin-adm/dm3-extract/store-dm3")
OUT = REX / "pipeline/out/gate2"
EVID = REX / "evidence"
VOX = 32.0

DT_MAX_MS = 200          # discard central differences spanning gaps > 0.2 s
SPAN_MIN_MS = 20         # central-difference span must cover >= 20 ms: measured on the
                         # val split, spans < 20 ms give p99.9 = 1394-4094 u/s (noise
                         # amplification of 0.125u MVD quantisation) vs true QWD
                         # |v_xy| p99.9 = 840; spans 20-40 ms give 916 (within 9 %)
JUMP_MAX_U = 250.0       # discard across 3D discontinuities > 250 u
MIN_N = 30               # voxels with fewer filtered samples get no speed claim
OPEN_P95 = 400.0         # brief's suggested open threshold (validated in classify)
CAP_U = 500.0            # the gate speed

CLASS_NAMES = {
    1: "EXCLUDED_WATER", 2: "EXCLUDED_LIFT", 3: "EXCLUDED_TELE",
    4: "INCLUDED_OPEN", 5: "INCLUDED_CONSTRAINED", 6: "INCLUDED_LOWDATA",
}

# ------------------------------------------------------------------ BSP parsing
LUMP_ENTITIES, LUMP_PLANES, LUMP_NODES, LUMP_LEAFS, LUMP_MODELS = 0, 1, 5, 10, 14
CONTENTS_EMPTY, CONTENTS_SOLID, CONTENTS_WATER, CONTENTS_SLIME, CONTENTS_LAVA = -1, -2, -3, -4, -5


class Bsp:
    def __init__(self, path: Path):
        d = path.read_bytes()
        lump = lambda i: struct.unpack_from("<ii", d, 4 + 8 * i)

        off, ln = lump(LUMP_PLANES)
        n = ln // 20
        pl = np.frombuffer(d, dtype="<f4", count=n * 5, offset=off).reshape(n, 5)
        self.pnormal = pl[:, :3].astype(np.float64)
        self.pdist = pl[:, 3].astype(np.float64)

        off, ln = lump(LUMP_NODES)
        n = ln // 24
        self.node_plane = np.zeros(n, np.int32)
        self.node_child = np.zeros((n, 2), np.int32)
        for i in range(n):
            p, c0, c1 = struct.unpack_from("<ihh", d, off + 24 * i)
            self.node_plane[i], self.node_child[i] = p, (c0, c1)

        off, ln = lump(LUMP_LEAFS)
        n = ln // 28
        self.leaf_contents = np.array(
            [struct.unpack_from("<i", d, off + 28 * i)[0] for i in range(n)], np.int32)

        off, _ = lump(LUMP_MODELS)
        self.headnode0 = struct.unpack_from("<i", d, off + 36)[0]  # model 0, hull 0
        self.model_bbox = lambda i: (
            struct.unpack_from("<fff", d, off + 64 * i),
            struct.unpack_from("<fff", d, off + 64 * i + 12))

        eoff, eln = lump(LUMP_ENTITIES)
        txt = d[eoff:eoff + eln].split(b"\0")[0].decode("latin-1")
        import re
        self.entities = [dict(re.findall(r'"([^"]+)"\s+"([^"]*)"', b))
                         for b in re.findall(r"\{(.*?)\}", txt, re.S)]

    def contents(self, p) -> int:
        n = self.headnode0
        while n >= 0:
            i = self.node_plane[n]
            side = 0 if float(np.dot(self.pnormal[i], p)) - self.pdist[i] >= 0 else 1
            n = self.node_child[n, side]
        return int(self.leaf_contents[-1 - n])

    def contents_robust(self, cx, cy, cz) -> int:
        """Voxel-center contents; if the center is inside a wall (traffic hugging a
        boundary voxel), fall back to majority over the 8 corners."""
        c = self.contents((cx, cy, cz))
        if c != CONTENTS_SOLID:
            return c
        votes = Counter()
        for dx in (-15.0, 15.0):
            for dy in (-15.0, 15.0):
                for dz in (-15.0, 15.0):
                    cc = self.contents((cx + dx, cy + dy, cz + dz))
                    if cc != CONTENTS_SOLID:
                        votes[cc] += 1
        return votes.most_common(1)[0][0] if votes else CONTENTS_EMPTY


def entity_volumes(bsp: Bsp):
    """func_plat swept volumes (+shaft above, expanded 32u) and trigger_teleport bboxes.

    Quake func_plat brushes are compiled at the TOP stop; at rest the plat sits
    `height` lower (default: brush height - 8). A rider's origin sweeps from
    (bottom top-surface + ~24) to (top-surface + ~24 + jump), so the exclusion
    volume spans z in [top_mins - travel, top_maxs + 64], xy expanded 32 u.
    """
    lifts, teles = [], []
    for e in bsp.entities:
        cn = e.get("classname", "")
        if not cn.startswith(("func_plat", "trigger_teleport")):
            continue
        idx = int(e["model"][1:])
        mins, maxs = bsp.model_bbox(idx)
        if cn == "func_plat":
            travel = float(e.get("height", (maxs[2] - mins[2]) - 8.0))
            lifts.append({
                "mins": [mins[0] - VOX, mins[1] - VOX, mins[2] - travel],
                "maxs": [maxs[0] + VOX, maxs[1] + VOX, maxs[2] + 64.0],
                "top_bbox": [list(mins), list(maxs)], "travel": travel})
        else:
            # a trigger fires when the PLAYER HULL touches it, so the effective
            # volume for player-origin samples is the bbox expanded by the hull
            # half-extents (16,16) xy and (-24,+32) z. The raw dm3 boxes are
            # 22x46x30 u - thinner than a voxel - so without this expansion no
            # voxel center ever lands inside (measured: 0 voxels classified).
            teles.append({"mins": [mins[0] - 16, mins[1] - 16, mins[2] - 32],
                          "maxs": [maxs[0] + 16, maxs[1] + 16, maxs[2] + 24],
                          "raw_bbox": [list(mins), list(maxs)],
                          "target": e.get("target", "?")})
    return lifts, teles


def _in_box(cx, cy, cz, box):
    """Voxel cube [c-16, c+16] intersects the box."""
    h = VOX / 2
    return all(box["mins"][i] <= c + h and c - h <= box["maxs"][i]
               for i, c in enumerate((cx, cy, cz)))


# ------------------------------------------------------------------ stage: stats
FILES_GLOB = f"{STORE}/trajectory_samples/split=*/**/*.parquet"

SPEED_CTES = f"""
WITH pos AS (
  SELECT demo_key, slot, t, x, y, z, lq,
         lag(t)  OVER w AS tm, lag(x)  OVER w AS xm, lag(y)  OVER w AS ym, lag(z) OVER w AS zm,
         lead(t) OVER w AS tp, lead(x) OVER w AS xp, lead(y) OVER w AS yp, lead(z) OVER w AS zp
  FROM read_parquet($files)
  WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL
  WINDOW w AS (PARTITION BY demo_key, slot ORDER BY t)
),
vel AS (
  SELECT demo_key, slot, t, x, y, z, lq,
         CASE WHEN tm IS NOT NULL AND tp IS NOT NULL
                   AND (t - tm) BETWEEN 1 AND {DT_MAX_MS}
                   AND (tp - t) BETWEEN 1 AND {DT_MAX_MS}
                   AND (tp - tm) >= {SPAN_MIN_MS}
                   AND sqrt((x-xm)*(x-xm)+(y-ym)*(y-ym)+(z-zm)*(z-zm)) <= {JUMP_MAX_U}
                   AND sqrt((xp-x)*(xp-x)+(yp-y)*(yp-y)+(zp-z)*(zp-z)) <= {JUMP_MAX_U}
              THEN sqrt((xp-xm)*(xp-xm)+(yp-ym)*(yp-ym)) / (tp - tm) * 1000.0
         END AS h
  FROM pos
),
med AS (
  SELECT demo_key, slot, x, y, z, lq, h,
         lag(h) OVER w2 AS hm, lead(h) OVER w2 AS hp
  FROM vel WHERE h IS NOT NULL
  WINDOW w2 AS (PARTITION BY demo_key, slot ORDER BY t)
),
filt AS (
  SELECT CAST(floor(x/{VOX}) AS INTEGER) AS ix,
         CAST(floor(y/{VOX}) AS INTEGER) AS iy,
         CAST(floor(z/{VOX}) AS INTEGER) AS iz,
         lq,
         CASE WHEN hm IS NOT NULL AND hp IS NOT NULL
              THEN hm + h + hp - greatest(hm, h, hp) - least(hm, h, hp)
              ELSE h END AS hf
  FROM med
)
"""


def _connect():
    import duckdb
    con = duckdb.connect()
    con.execute("SET threads=12")
    con.execute("SET memory_limit='300GB'")
    con.execute("SET preserve_insertion_order=false")
    return con


def stage_stats():
    OUT.mkdir(parents=True, exist_ok=True)
    con = _connect()
    files = sorted(glob.glob(FILES_GLOB, recursive=True))
    con.execute("COPY (" + SPEED_CTES + """
        SELECT ix, iy, iz, count(*) AS n,
               quantile_cont(hf, 0.50) AS p50,
               quantile_cont(hf, 0.95) AS p95,
               quantile_cont(hf, 0.99) AS p99,
               quantile_cont(hf, 0.999) AS p999,
               max(hf) AS mx,
               count(*) FILTER (lq IS NOT NULL)          AS n_lq,
               count(*) FILTER (lq IS NOT NULL AND lq>0) AS n_wet
        FROM filt GROUP BY ix, iy, iz
        ) TO '""" + str(OUT / "voxel_stats.parquet") + "' (FORMAT PARQUET)",
        {"files": files})
    n = con.execute(f"SELECT count(*), sum(n) FROM read_parquet('{OUT}/voxel_stats.parquet')").fetchone()
    print(f"voxel_stats.parquet: {n[0]} voxels, {n[1]} filtered samples", flush=True)


# --------------------------------------------------------------- stage: classify
LANDMARKS = {  # item_nodes from evidence/corpus_sufficiency.json + atlas tele/window
    "quad": (952, 296, 56), "ratop": (256, -704, 304), "ralow-ng-tunnel": (-64, -704, -40),
    "ya": (1232, -904, -48), "ssg-ya": (1776, -656, -48), "sng": (-512, 448, 96),
    "mega-sng": (-720, 80, 160), "mega-hill": (564, -48, -192), "mega-pent": (1840, 624, -204),
    "rl": (1520, 496, -112), "gl-water": (1216, 240, -416), "lg-water": (1544, -192, -416),
    "ring": (240, -32, 56), "pent": (1008, 800, -296), "window": (1328, 544, 44),
    "tele-ya-in": (1180, -904, 0), "tele-sng-in": (-508, -448, 24),
    "tele-sng-out": (224, -320, 48),
}


def _load_voxels(con):
    rows = con.execute(f"""
        SELECT ix, iy, iz, n, p50, p95, p99, p999, mx, n_lq, n_wet
        FROM read_parquet('{OUT}/voxel_stats.parquet') ORDER BY ix, iy, iz""").fetchall()
    a = np.array(rows, dtype=np.float64)
    return (a[:, 0].astype(np.int32), a[:, 1].astype(np.int32), a[:, 2].astype(np.int32),
            a[:, 3].astype(np.int64), a[:, 4], a[:, 5], a[:, 6], a[:, 7], a[:, 8],
            a[:, 9].astype(np.int64), a[:, 10].astype(np.int64))


def stage_classify():
    bsp = Bsp(BSP_PATH)
    lifts, teles = entity_volumes(bsp)
    print("lifts:", json.dumps(lifts), "\nteles:", json.dumps(teles), flush=True)
    con = _connect()
    ix, iy, iz, n, p50, p95, p99, p999, mx, n_lq, n_wet = _load_voxels(con)
    m = len(ix)
    cx, cy, cz = (ix + 0.5) * VOX, (iy + 0.5) * VOX, (iz + 0.5) * VOX

    cls = np.zeros(m, np.uint8)
    contents = np.array([bsp.contents_robust(cx[i], cy[i], cz[i]) for i in range(m)], np.int32)
    # Water by BSP leaf contents OR by the measured QWD liquid flag: voxels in the
    # air gap just above a water leaf (surface swimming, player origin above the
    # surface) test EMPTY in the BSP but are >50 % wet in the corpus - measured
    # 100 % wet for the three zones this catches. Swim physics caps them equally.
    lq_wet = (n_lq >= 50) & (n_wet > 0.5 * np.maximum(n_lq, 1))
    for i in range(m):
        if contents[i] in (CONTENTS_WATER, CONTENTS_SLIME, CONTENTS_LAVA) or lq_wet[i]:
            cls[i] = 1
        elif any(_in_box(cx[i], cy[i], cz[i], b) for b in lifts):
            cls[i] = 2
        elif any(_in_box(cx[i], cy[i], cz[i], b) for b in teles):
            cls[i] = 3
        elif n[i] < MIN_N:
            cls[i] = 6
        elif p999[i] < CAP_U:
            # "human cap" criterion: p99.9, not raw max — the derived max is
            # contaminated by MVD warp artifacts (measured up to 10 895 u/s derived
            # vs 3 135 u/s true QWD max); p99.9 tracks true velocities within 9 %.
            cls[i] = 5
        else:
            cls[i] = 4

    # cross-validation: QWD liquid flag vs BSP water classification
    has_lq = n_lq > 0
    wet_frac = np.divide(n_wet, n_lq, out=np.zeros(m), where=has_lq)
    water_sel = cls == 1
    print(f"lq cross-check: water voxels with lq data: {int((water_sel & has_lq).sum())}, "
          f"mean wet_frac {wet_frac[water_sel & has_lq].mean():.3f}; "
          f"dry-class voxels mean wet_frac {wet_frac[(~water_sel) & has_lq].mean():.3f}", flush=True)

    # threshold diagnostics for the OPEN definition
    inc = cls == 4
    print(f"OPEN diag: of {inc.sum()} max>=500 voxels, {int((p95[inc] < OPEN_P95).sum())} "
          f"have p95<{OPEN_P95:.0f} (behaviourally slow but physically uncapped)", flush=True)

    # connected components (26-conn) over constrained voxels -> named zones
    keyset = {}
    con_idx = np.where(cls == 5)[0]
    for i in con_idx:
        keyset[(ix[i], iy[i], iz[i])] = i
    seen, clusters = set(), []
    for k in keyset:
        if k in seen:
            continue
        stack, comp = [k], []
        seen.add(k)
        while stack:
            c = stack.pop()
            comp.append(keyset[c])
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        nb = (c[0] + dx, c[1] + dy, c[2] + dz)
                        if nb in keyset and nb not in seen:
                            seen.add(nb)
                            stack.append(nb)
        clusters.append(np.array(comp))
    clusters.sort(key=lambda c: -int(n[c].sum()))

    lm_names = list(LANDMARKS)
    lm_pos = np.array([LANDMARKS[k] for k in lm_names], np.float64)
    zone_of = np.full(m, -1, np.int32)
    zones = []
    name_count = defaultdict(int)
    for comp in clusters:
        w = n[comp].astype(np.float64)
        cen = np.array([np.average(cx[comp], weights=w), np.average(cy[comp], weights=w),
                        np.average(cz[comp], weights=w)])
        if int(w.sum()) < 500 or len(comp) < 4:
            zname = "constrained-misc"
        else:
            d = np.linalg.norm(lm_pos - cen, axis=1)
            base = lm_names[int(d.argmin())]
            name_count[base] += 1
            zname = base if name_count[base] == 1 else f"{base}-{name_count[base]}"
        zid = next((z["id"] for z in zones if z["name"] == zname), None)
        if zid is None:
            zid = len(zones)
            zones.append({"id": zid, "name": zname, "class": "INCLUDED_CONSTRAINED",
                          "voxels": 0, "samples": 0, "centroid": [round(v, 1) for v in cen],
                          "bounds": None})
        z = zones[zid]
        z["voxels"] += len(comp)
        z["samples"] += int(w.sum())
        bb = [[float(cx[comp].min() - VOX / 2), float(cy[comp].min() - VOX / 2), float(cz[comp].min() - VOX / 2)],
              [float(cx[comp].max() + VOX / 2), float(cy[comp].max() + VOX / 2), float(cz[comp].max() + VOX / 2)]]
        z["bounds"] = bb if z["bounds"] is None else [
            [min(a, b) for a, b in zip(z["bounds"][0], bb[0])],
            [max(a, b) for a, b in zip(z["bounds"][1], bb[1])]]
        zone_of[comp] = zid
    print(f"{len(clusters)} constrained components -> {len(zones)} named zones", flush=True)

    np.savez_compressed(
        OUT / "voxel_classes.npz",
        ix=ix.astype(np.int16), iy=iy.astype(np.int16), iz=iz.astype(np.int16),
        cls=cls, n=n.astype(np.uint32), p50=p50.astype(np.float32),
        p95=p95.astype(np.float32), p99=p99.astype(np.float32),
        p999=p999.astype(np.float32), mx=mx.astype(np.float32),
        zone=zone_of.astype(np.int16), contents=contents.astype(np.int8))
    (OUT / "voxel_classes_meta.json").write_text(json.dumps({
        "voxel_u": VOX, "index": "world = index*32 .. index*32+32 (floor(coord/32))",
        "classes": CLASS_NAMES, "zones": zones,
        "lifts": lifts, "teles": teles,
        "filters": {"dt_max_ms": DT_MAX_MS, "jump_max_u": JUMP_MAX_U, "min_n": MIN_N,
                    "speed": "horizontal central difference, 3-sample median filtered"},
    }, indent=1))
    # zone_map for the exact sample-level second pass: named zones + class pseudo-zones
    with open(OUT / "zone_map.csv", "w") as f:
        f.write("ix,iy,iz,zkey\n")
        for i in range(m):
            zkey = zones[zone_of[i]]["name"] if zone_of[i] >= 0 else CLASS_NAMES[cls[i]]
            f.write(f"{ix[i]},{iy[i]},{iz[i]},{zkey}\n")
    con.execute(f"COPY (SELECT * FROM read_csv('{OUT}/zone_map.csv')) TO '{OUT}/zone_map.parquet'")
    print("wrote voxel_classes.npz, voxel_classes_meta.json, zone_map.parquet", flush=True)


# -------------------------------------------------------------- stage: zonestats
def stage_zonestats():
    con = _connect()
    files = sorted(glob.glob(FILES_GLOB, recursive=True))
    con.execute(f"CREATE TEMP TABLE zone_map AS SELECT * FROM read_parquet('{OUT}/zone_map.parquet')")
    con.execute("CREATE TEMP TABLE zs AS " + SPEED_CTES + """
        , tagged AS (
          SELECT z.zkey, f.hf FROM filt f JOIN zone_map z USING (ix, iy, iz))
        SELECT zkey, count(*) AS n,
               quantile_cont(hf, 0.50) AS p50, quantile_cont(hf, 0.95) AS p95,
               quantile_cont(hf, 0.99) AS p99, quantile_cont(hf, 0.999) AS p999,
               max(hf) AS mx, avg(hf) AS mean
        FROM tagged GROUP BY zkey""", {"files": files})
    con.execute(f"COPY zs TO '{OUT}/zone_stats.parquet' (FORMAT PARQUET)")
    for r in con.execute("SELECT * FROM zs ORDER BY n DESC").fetchall():
        print(r, flush=True)


# ----------------------------------------------------------------- stage: report
# Curated interpretations of the auto-named (nearest-landmark) constrained zones,
# from cross-checking each zone's bounds against the BSP geometry, the lift/tele
# volumes and the item positions. Auto names stay as stable IDs.
ZONE_DESC = {
    "ratop": "RA-toppplattformen (campläge ovanpå RA-hyllan, z 288-352)",
    "constrained-misc": "spridda småkomponenter över hela kartan: kanter, hörn, dörrposter",
    "rl": "RL-plattformen (ståstället runt RL-spawnen)",
    "quad": "avsatsen/gången ovanpå översta hissen (hisstopp z~191), mot quad-/SNG-sidan",
    "mega-sng": "mega-hyllan i SNG-rummet",
    "pent": "hisschaktets norra avsatser (mellanlandningar bakom hiss 2/3)",
    "ya": "YA-stället (gula rustningens golvyta)",
    "tele-sng-in": "trappschaktet mellan ring-planets undervåning och t2-telen/RA-låg",
    "ssg-ya": "SSG-hyllan vid YA-gården",
    "ratop-2": "kantavsatsen/trappsteget öster om RA-toppen",
    "ralow-ng-tunnel": "NG-tunnelmynningen vid RA-låg (vertikalt schakt i västväggen)",
    "sng": "SNG-rummets trånga väst-/golvpartier",
    "sng-2": "SNG-rummets södra golv-/trappartier",
    "sng-3": "SNG-rummets östra golv-/trappartier",
    "sng-4": "SNG-rummets nedre golvficka",
    "sng-5": "SNG-rummets norra hylla",
    "window": "fönstret (window) mellan quad-övervåningen och RL-området",
    "ssg-ya-2": "östra trappan/rampen från YA-gården ner mot RL/mega-pent",
    "quad-2": "smala övervåningspassagen ring<->quad (z 32-64)",
    "ring": "nedre korridorshörnet under ring-planet",
    "mega-hill": "smala spalten vid kullens mega (hill-mega)",
    "mega-hill-2": "smala spalten vid kullens mega, östra delen",
    "tele-sng-out": "t2-telens utgångsplatta (destination, ej triggervolym)",
}


def stage_report():
    meta = json.loads((OUT / "voxel_classes_meta.json").read_text())
    d = np.load(OUT / "voxel_classes.npz")
    cls, n, zone = d["cls"], d["n"].astype(np.int64), d["zone"]
    con = _connect()
    zs = {r[0]: dict(zip(("n", "p50", "p95", "p99", "p999", "max", "mean"), r[1:]))
          for r in con.execute(
              f"SELECT zkey, n, p50, p95, p99, p999, mx, mean FROM read_parquet('{OUT}/zone_stats.parquet')").fetchall()}
    total_vox, total_n = len(cls), int(n.sum())
    classes = {}
    for code, name in CLASS_NAMES.items():
        sel = cls == code
        stats = zs.get(name)  # pseudo-zone rows carry exact sample-level stats
        if name == "INCLUDED_CONSTRAINED":  # split across named zones in zone_stats
            zn = [z["name"] for z in meta["zones"]]
            agg_n = sum(zs[z]["n"] for z in zn if z in zs)
            stats = {"n": agg_n, "note": "see zones[] for exact per-zone percentiles"}
        classes[name] = {
            "voxels": int(sel.sum()), "samples": int(n[sel].sum()),
            "volume_share": round(float(sel.sum()) / total_vox, 4),
            "traffic_share": round(float(n[sel].sum()) / total_n, 4),
            "sample_level_hspeed": {k: (round(v, 1) if isinstance(v, float) else v)
                                    for k, v in stats.items()} if stats else None,
        }
    zones_out = []
    for z in meta["zones"]:
        st = zs.get(z["name"])
        zones_out.append({**z, "desc": ZONE_DESC.get(z["name"]),
                          "hspeed": {k: round(v, 1) if isinstance(v, float) else v
                                     for k, v in st.items()} if st else None})
    out = {
        "generated": "pipeline/gate2_zones.py",
        "map": "dm3", "voxel_u": VOX,
        "corpus": {"store": str(STORE / "trajectory_samples"), "raw_rows": 907977350,
                   "filtered_speed_samples": total_n},
        "filters": meta["filters"] | {"span_min_ms": SPAN_MIN_MS,
                                      "speed_metric": "horizontal central difference, 3-sample median filtered"},
        "thresholds": {"cap_u": CAP_U, "open_p95_u": OPEN_P95, "min_n": MIN_N,
                       "constrained_criterion": "p99.9 human hspeed < 500 (raw max is warp-contaminated)"},
        "summary": {"voxels_with_traffic": total_vox, "classes": classes},
        "zones": zones_out,
        "lifts": meta["lifts"], "teles": meta["teles"],
        "gate_recommendation": {
            "verdict": "exclude water/lift/tele is NOT sufficient alone - 6.6 % of traffic "
                       "sits in dry zones with measured human ceilings 345-497 u/s (< 500); "
                       "a flat 500-gate over them teaches the agent to avoid those zones",
            "formula": {
                "counted": "samples in INCLUDED_OPEN u INCLUDED_CONSTRAINED voxels",
                "not_counted": "EXCLUDED_WATER, EXCLUDED_LIFT, EXCLUDED_TELE, INCLUDED_LOWDATA",
                "target_open_u": CAP_U,
                "target_constrained": "0.8 * zone p99.9 (human ceiling), see zone_targets",
                "score": "mean over validation samples of v_h / T(voxel)",
                "pass": "score >= 1.0 AND mean(v_h | INCLUDED_OPEN) > 500 "
                        "AND >= 70 % of INCLUDED_OPEN voxels visited (anti-loop guard)",
            },
            "zone_targets_u": {z["name"]: round(0.8 * min(z["hspeed"]["p999"], CAP_U), 1)
                               for z in zones_out if z.get("hspeed")},
        },
    }
    (EVID / "gate2_zones.json").write_text(json.dumps(out, indent=1))
    print("wrote", EVID / "gate2_zones.json", flush=True)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("stats", "all"):
        stage_stats()
    if stage in ("classify", "all"):
        stage_classify()
    if stage in ("zonestats", "all"):
        stage_zonestats()
    if stage in ("report", "all"):
        stage_report()
