"""Generera rutt-states (reverse curriculum steg -1) ur bottens verifierade
lyckade rq-SO-bana (traj_63G ep1, detektor v7.3-klippet 'ring→quad SO — lyckat').

Körning:
    PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/gen_route_states.py \
        <clips_63G.json> rl/data/route_states_rq_so.json

Metod: klippets path är [x,y,z,fart] per 2 ticks (dt 0.026). För varje inre
index i tas pos=path[i][:3], vel=centraldifferens (path[i+1]-path[i-1])/(2·dt),
yaw=horisontella hastighetens riktning. Detta är RIKTIGA pmove-tillstånd —
ballistiskt konsistenta per konstruktion (skeptikerfynd 1-fixen) och bbox-
giltiga (fynd 3-fixen: ingen jitter läggs på).

Filter:
- endast indexfönstret [I0, I1] (första hoppets ansats → strax före sista
  landningen),
- states inom completion-radien+32 av målet med z >= ref-24 KASSERAS
  (grundad spawn inne i målzonen hade gjort +12-bonusen till ett gratis
  hopp-på-stället; luftstates PÅ väg in behålls som curriculumets lätta ände).

Ingen mänsklig BC: källan är agentens egen bana, och den används enbart som
RESET-fördelning (aldrig som handlingssupervision).
"""
import json
import sys

import numpy as np

TARGET_2D = (906.5, 50.6)     # rq-SO landing_2d (gate_takeoff_states.json)
REF_Z = 56.0                  # ringens origo-nivå (states z=48 + origo 8→56)
COMPLETION_R = 192.0          # måste spegla Gate2Config.completion_radius
I0, I1 = 28, 175              # ansats → strax före sista landningen


def main(clips_path, out_path):
    clips = json.load(open(clips_path))["clips"]
    clip = next(c for c in clips if c.get("verdict") == "godkänd"
                and "lyckat" in c.get("label", ""))
    p = np.asarray([q[:3] for q in clip["path"]], dtype=float)
    dt = float(clip["dt"])
    states, dropped, disc = [], 0, 0
    for i in range(max(I0, 1), min(I1, len(p) - 1)):
        vel = (p[i + 1] - p[i - 1]) / (2.0 * dt)
        # Skeptikerfynd r2:4: centraldiffen SMETAR över og-diskontinuiteter
        # (avstamp/landning) och ger vz ingen pmove-bana passerar (~halva
        # hopp-vz på grundade punkter). Ballistisk flygning ändrar vz med
        # g·dt ≈ 20.8 per intervall — kassera index där fram-/bakåt-vz
        # skiljer > 120 (avstamp ~+270, landning ~−200-300 mot 0).
        vz_bwd = (p[i][2] - p[i - 1][2]) / dt
        vz_fwd = (p[i + 1][2] - p[i][2]) / dt
        if abs(vz_fwd - vz_bwd) > 120.0:
            disc += 1
            continue
        d_tgt = float(np.hypot(p[i][0] - TARGET_2D[0], p[i][1] - TARGET_2D[1]))
        if d_tgt <= COMPLETION_R + 32.0 and p[i][2] >= REF_Z - 24.0:
            dropped += 1
            continue
        states.append({
            "pos": [round(float(x), 2) for x in p[i]],
            "vel": [round(float(v), 2) for v in vel],
            "yaw": round(float(np.degrees(np.arctan2(vel[1], vel[0]))), 2),
            "target_2d": list(TARGET_2D),
            "ref_z": REF_Z,
            "src_idx": i,
        })
    out = {
        "generator": "evidence/repro/gen_route_states.py (2026-08-03 natt)",
        "källa": f"traj_63G ep{clip['ep']} — '{clip['label']}' (v7.3-klipp, "
                 f"{len(clip['path'])} punkter, dt {dt})",
        "motiv": "rotorsaksfixen: enkelhopp fysikaliskt omöjligt; verifierade "
                 "rutten är flerhopp — states är riktiga pmove-tillstånd ur "
                 "agentens egen lyckade bana (reset-fördelning, ingen BC)",
        "filter": f"index [{I0},{I1}], målzon-drop {dropped}, "
                  f"og-diskontinuitetsdrop {disc} (|dvz| > 120; skeptikerfynd r2:4)",
        "states": states,
    }
    json.dump(out, open(out_path, "w"), ensure_ascii=False, indent=1)
    print(f"{len(states)} states skrivna ({dropped} målzon-, {disc} diskontinuitets-droppade) → {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
