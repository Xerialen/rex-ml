"""Build the one replay page: the owner's reference demos and the policy's attempts, side by side.

Two datasets, one file, grouped by route — because the only question worth asking of either is how
they differ on the same journey, and two pages cannot be scrubbed against each other.

Frames are unified at 25 bytes (`x, y, z, yaw` f32, flags u8, `speed` f32, `pitch` f32). The policy
has no pitch — its observation pins that axis at 0.0 because the environment has no view control
there — so its pitch column is written as zero and the page's first-person camera is level for it.
That is a real difference between the two subjects and the page says so rather than hiding it behind
a shared format.

Every record also carries its coverage block from `pipeline.coverage`, so the page can show what the
numbers rest on: how many distinct trajectories the attempts actually produced, and how many of the
map's approaches to the target were exercised.
"""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

import numpy as np

from . import cohort_routes as C
from . import coverage as CV
from . import race
from . import corridor_replay as CR
from . import record_strict as RS
from . import record_reference as RR

OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/replay")
SCRATCH = Path("/tmp/claude-1001/-home-benjamin-adm-rex-ml/003dd697-8855-417d-9d80-53960851ebcf/scratchpad")
TEMPLATE = Path("/home/benjamin-adm/rex-ml/pipeline/replay_template.html")


def widen(blob: bytes, runs: list[dict]) -> tuple[bytes, list[dict]]:
    """Re-pack 21-byte policy frames as 25-byte frames with a zero pitch column."""
    out = bytearray()
    new = []
    for r in runs:
        off = len(out)
        for i in range(r["n_frames"]):
            b = r["offset"] + i * 21
            x, y, z, yaw = struct.unpack_from("<ffff", blob, b)
            fl = blob[b + 16]
            sp, = struct.unpack_from("<f", blob, b + 17)
            out += struct.pack("<ffffBff", x, y, z, yaw, fl, sp, 0.0)
        new.append(dict(r, offset=off))
    return bytes(out), new


# Who produced a run. The page's own field names — "reference", "race_v7 ing.0", "greedy" — say how
# the run was decoded, not whose it is, and the owner asked for that to be unmistakable: his own
# recordings, the trained policy, and the hand-written controller are three different kinds of claim.
SOURCE_LABEL = {
    "owner": ("DIN INSPELNING", "ägarens egna .qwd-demon, lästa med qw-demo-miners QWD v2-extraktor"),
    "ml": ("ML-POLICY", "tränad rörelsepolicy, miljöns egna float32-positioner per servertick"),
    "analytic": ("ANALYTISK", "handskriven strafe-jumper — inget maskininlärt, bara fysikens optimum"),
}


def annotate_source(records: list[dict]) -> None:
    """Tag every record with who produced it, and put that first in the label the page shows."""
    for rec in records:
        dec = rec.get("decode", "")
        if dec == "reference":
            src = "owner"
        elif dec == "analytisk":
            src = "analytic"
        else:
            src = "ml"
        rec["source"] = src
        short, long = SOURCE_LABEL[src]
        rec["source_label"] = short
        rec["source_note"] = long
        gl = rec.get("group_label", dec)
        # Case-insensitive: the corridor's own label already begins with "analytisk" in lower case,
        # and a case-sensitive check produced "ANALYTISK · analytisk — ...".
        if not gl.upper().startswith(short.upper()):
            rec["group_label"] = f"{short} · {gl}"


def render_only() -> Path:
    """Re-render the page from the already-recorded index and frames.

    Recording the strict protocol is ~1300 episodes. Iterating on the page's own interface should not
    pay that, and re-recording would also change the sample, which would silently move the numbers
    while the only thing being edited is a selector.
    """
    index = json.loads((OUT / "index_all.json").read_text())
    # Drop the superseded race_v5 dm3 records. They were trained and recorded at TICK_DT = 0.014,
    # which is not the tick the game runs at, and leaving them next to race_v7 under the same route
    # heading mixes two physics regimes without saying so. The corridor's race_v5 run stays, because
    # there it is the labelled contrast against the analytic ceiling.
    before = len(index["records"])
    index["records"] = [r for r in index["records"]
                        if not (r.get("map") != "100m" and r.get("decode") in ("greedy", "sampled"))]
    print(f"tog bort {before - len(index['records'])} föråldrade race_v5-poster (fel tickfrekvens)")
    # index["ckpt"] is kept as stored: the recorded index already names its checkpoint and date,
    # and a re-render must not restamp it with another build's description.
    annotate_source(index["records"])
    blob = (OUT / "frames_all.bin").read_bytes()
    geo = base64.b64encode((OUT / "dm3_geo.bin").read_bytes()).decode()
    geo2 = base64.b64encode((OUT / "m100_geo.bin").read_bytes()).decode()
    html = (TEMPLATE.read_text()
            .replace("__INDEX_JSON__", json.dumps(index, default=float))
            .replace("__GEO_B64__", geo)
            .replace("__GEO2_B64__", geo2)
            .replace("__FRAMES_B64__", base64.b64encode(blob).decode())
            .replace("<title>dm3 — ML-policyns rörelse, tick för tick</title>",
                     "<title>dm3 — referensdemos mot ML-policyn, tick för tick</title>")
            .replace("<h1>dm3 — <b>ML-policyns rörelse</b>, tick för tick</h1>",
                     "<h1>dm3 — <b>referens mot policy</b>, tick för tick</h1>"))
    p = SCRATCH / "dm3-replay.html"
    p.write_text(html)
    print(f"renderade om {len(index['records'])} poster utan ny inspelning -> {p} "
          f"({len(html) / 1e6:.2f} MB)")
    return p


def main():
    import sys
    if "--reuse" in sys.argv:
        render_only()
        return
    blob = bytearray()
    records: list[dict] = []

    # --- the owner's reference demos -------------------------------------------------------
    for demo_name, route in RR.DEMO_ROUTE.items():
        path = RR.DEMO_DIR / demo_name
        if not path.exists():
            print(f"saknas, hoppas över: {demo_name}")
            continue
        try:
            b, rec = RR.build_record(path, route)
        except Exception as e:                                  # noqa: BLE001
            print(f"kunde inte läsa {demo_name}: {e}")
            continue
        rec["runs"] = [dict(r, offset=r["offset"] + len(blob)) for r in rec["runs"]]
        blob += b
        CV.attach(rec, attempts=1, distinct=1, approaches_modelled=0, approaches_tested=1,
                  note="one recorded run by the owner; not a sample of anything")
        rec["coverage"]["warnings"] = [
            "a single recorded run — it is the reference, not a distribution"]
        records.append(rec)
        print(f"referens {demo_name:38s} -> {route:22s} {rec['runs'][0]['n_frames']:4d} tick")

    # --- the strict protocol on race_v9, which is what the reported numbers are ------------------
    # The stale race_v5 dm3 attempts (index_v5.json, greedy/sampled, recorded at the wrong tick
    # rate) are deliberately NOT carried over: only the current checkpoint's records belong next to
    # the reference demos. Verdicts come from the canonical strict eval JSON, whose gate also
    # includes the manoeuvre and envelope columns this recorder does not measure.
    strict_json = json.loads(Path(
        "/home/benjamin-adm/rex-ml/pipeline/out/strict/strict_race_v9.json").read_text())
    verdicts = {r["name"]: bool(r["passes_strict"]) for r in strict_json["routes"]}
    print(f"\nstrikt prov, race_v9 (ruttdomar ur strict_race_v9.json: "
          f"{sum(verdicts.values())}/{len(verdicts)} godkända):")
    sblob, srecs = RS.build(len(blob), "/home/benjamin-adm/rex-ml/pipeline/out/race/race_v9.pt",
                            n=48, route_verdicts=verdicts)
    blob += sblob
    records += srecs

    # --- the 100m corridor: the owner's speed gate, on its own map ------------------------------
    cblob, crecs = CR.build(len(blob), "/home/benjamin-adm/rex-ml/pipeline/out/race/race_v9.pt", n=8)
    blob += cblob
    for rec in crecs:
        CV.attach(rec, attempts=rec["attempts"], distinct=rec["distinct_trajectories"],
                  approaches_modelled=1, approaches_tested=1,
                  note="one straight corridor; there is only one way down it")
        records.append(rec)
        print(f"100m     {rec['decode']:22s} topp {rec['peak_speed_ups']:6.1f} u/s, "
              f"ankomst {rec['arrival_rate'] * 100:5.1f}%")

    # route order: reference first within each route, routes in gate order
    order = {r.name: i for i, r in enumerate(C.ROUTES)}
    order["100m_korridor"] = -1          # the gate that comes before the routes, listed first
    records.sort(key=lambda r: (order.get(r["route"], 99),
                                0 if r["decode"] == "reference" else 1, r["decode"]))

    index = {
        "ckpt": ("dina referensdemon + race_v9 — strikt prov 2026-07-30, "
                 f"{sum(verdicts.values())}/{len(verdicts)} rutter godkända"),
        "tick_dt": C.TICK_DT,
        "arrive_box": C.ARRIVE_BOX,
        "arrive_z": C.ARRIVE_Z,
        "frame_bytes": 25,
        "peak_gate_ups": 790,
        "geo_map": "dm3",
        "geo2_map": "100m",
        "has_pitch": True,
        "ground_is_derived": True,
        "note": ("Två datamängder i samma fil. REFERENS är ägarens egna .qwd-inspelningar, lästa med "
                 "qw-demo-miners strikta QWD v2-extraktor: origin och hastighet ur serverns "
                 "playerinfo, blickvinklar och knapptryck ur spelarens dem_cmd, en rad per "
                 "servertick. POLICY är miljöns egna float32-positioner, också en rad per tick. "
                 "MARK* är härlett för referensen (QuakeWorld sänder ingen markflagga; vz = 0 "
                 "används, vilket håller på 71,5 % av tickarna mot 74,5 % i korpusen) och avläst för "
                 "policyn. Policyn har ingen pitch — miljön har ingen blickstyrning i den axeln — så "
                 "dess förstapersonsvy är vågrät. ▪ = väggkontakt. Policyposterna är det STRIKTA "
                 "provets egna körningar (race_v9): samplad avkodning, 48 episoder per ingång, "
                 "varav ett urval sparas som bildrutor — statistiken i gruppetiketten kommer från "
                 "alla 48, och GODKÄND/ej godkänd är strict_race_v9.json:s ruttdom, vars grind "
                 "också räknar manöver- och höljeskolumnerna. "
                 "LUFTSEGMENTEN under tidslinjen är körningens sammanhängande sträckor utan "
                 "markkontakt, klickbara till det tick avstampet sker. Klassningen frågar först vad "
                 "som finns UNDER flykten: GAPHOPP = golvet längs banan ligger mer än 96 u under den "
                 "lägsta av de två landningsytorna, alltså kostar en miss inte tid utan sätter "
                 "spelaren på en annan nivå; GAPHOPP UPPFÖR är samma sak men landningen ligger "
                 "högre än avstampet, vilket är svårare. Utan tomrum under gäller de svagare "
                 "skillnaderna: BUREN = längre än avstampsfarten gånger ett hopps 0,675 s hängtid, "
                 "FALL = mer höjd tappad än ett hopp vinner, HOPP = vanligt hopp. "
                 "Referensdemot gör ett GAPHOPP UPPFÖR på 144 u över 376 u tomrum — upp på RL-boxens "
                 "fönsterkarm. Policyn gör det inte."),
        "records": records,
    }
    annotate_source(records)
    (OUT / "frames_all.bin").write_bytes(bytes(blob))
    (OUT / "index_all.json").write_text(json.dumps(index, indent=1, default=float))

    geo = base64.b64encode((OUT / "dm3_geo.bin").read_bytes()).decode()
    geo2 = base64.b64encode((OUT / "m100_geo.bin").read_bytes()).decode()
    fr = base64.b64encode(bytes(blob)).decode()
    html = (TEMPLATE.read_text()
            .replace("__INDEX_JSON__", json.dumps(index, default=float))
            .replace("__GEO_B64__", geo)
            .replace("__GEO2_B64__", geo2)
            .replace("__FRAMES_B64__", fr)
            .replace("<title>dm3 — ML-policyns rörelse, tick för tick</title>",
                     "<title>dm3 — referensdemos mot ML-policyn, tick för tick</title>")
            .replace("<h1>dm3 — <b>ML-policyns rörelse</b>, tick för tick</h1>",
                     "<h1>dm3 — <b>referens mot policy</b>, tick för tick</h1>"))
    p = SCRATCH / "dm3-replay.html"
    p.write_text(html)
    print(f"\n{len(records)} poster, {len(blob) / 1e6:.2f} MB bildrutor, sida {len(html) / 1e6:.2f} MB -> {p}")


if __name__ == "__main__":
    main()
