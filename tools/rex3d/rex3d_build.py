"""Bygger rex-dm3-3d.html: dm3-geometri + korpusheat (atlas-pipelinen) +
RL-bottens greedy-banor (rex_trajectories.json) i en 3D-artefakt."""
import base64, json, re, struct
from pathlib import Path

SCRATCH = Path(__file__).parent
BSP = Path("/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/dm3.bsp")

# ---- entiteter (samma extraktion som atlas_prep) ----
data = BSP.read_bytes()
off, ln = struct.unpack_from("<ii", data, 4)
txt = data[off:off + ln].split(b"\0")[0].decode("latin-1")
ents = [dict(re.findall(r'"([^"]+)"\s+"([^"]*)"', b)) for b in re.findall(r"\{(.*?)\}", txt, re.S)]

def org(e):
    return [float(v) for v in e["origin"].split()]

NAMES = {
    "weapon_rocketlauncher": ("RL", "weapon"), "weapon_grenadelauncher": ("GL", "weapon"),
    "weapon_supernailgun": ("SNG", "weapon"), "weapon_nailgun": ("NG", "weapon"),
    "weapon_supershotgun": ("SSG", "weapon"), "weapon_lightning": ("LG", "weapon"),
    "item_armorInv": ("RA", "armor"), "item_armor2": ("YA", "armor"),
    "item_artifact_super_damage": ("Quad", "power"),
    "item_artifact_invulnerability": ("Pent", "power"),
    "item_artifact_invisibility": ("Ring", "power"),
}
items, spawns = [], []
for e in ents:
    cn = e.get("classname", "")
    if cn in NAMES:
        nm, kind = NAMES[cn]
        items.append({"name": nm, "kind": kind, "pos": org(e)})
    elif cn == "item_health" and e.get("spawnflags") == "2":
        items.append({"name": "Mega", "kind": "mega", "pos": org(e)})
    elif cn == "info_player_deathmatch":
        spawns.append({"name": f"spawn {len(spawns) + 1}", "kind": "spawn", "pos": org(e)})

mo, _ = struct.unpack_from("<ii", data, 4 + 8 * 14)
def model_center(i):
    b = mo + 64 * i
    mins = struct.unpack_from("<fff", data, b)
    maxs = struct.unpack_from("<fff", data, b + 12)
    return [(a + z) / 2 for a, z in zip(mins, maxs)]
dests = {e["targetname"]: org(e) for e in ents if e.get("classname") == "info_teleport_destination"}
teles = []
for e in ents:
    if e.get("classname") == "trigger_teleport":
        teles.append({"from": model_center(int(e["model"][1:])), "to": dests[e["target"]],
                      "name": "tele " + e["target"]})
lifts = []
for e in ents:
    if e.get("classname") == "func_plat":
        idx = int(e["model"][1:])
        b = mo + 64 * idx
        lifts.append({"name": "hiss", "mins": list(struct.unpack_from("<fff", data, b)),
                      "maxs": list(struct.unpack_from("<fff", data, b + 12))})

# ---- botbanor ----
traj = json.load(open(SCRATCH / "rex_trajectories.json"))
for ep in traj["episodes"]:
    ep["path"] = ep["path"][::2]          # var 4:e tick ≈ 28 u mellanrum — jämnt nog

metrics = jumpgates = None
mfile = Path.home() / "rex-ml" / "evidence" / "gate_metrics_history.json"
jfile = Path.home() / "rex-ml" / "evidence" / "jump_gates_latest.json"
if mfile.exists():
    metrics = json.load(open(mfile))
if jfile.exists():
    jumpgates = json.load(open(jfile))

DATA = {"items": items, "spawns": spawns, "teles": teles, "lifts": lifts, "traj": traj,
        "metrics": metrics, "jumpgates": jumpgates}

html = (SCRATCH / "rex3d_template.html").read_text()
html = html.replace("__DATA__", json.dumps(DATA, ensure_ascii=False))
html = html.replace("__GEO__", (SCRATCH / "atlas_geo.b64").read_text().strip())
html = html.replace("__HEAT__", (SCRATCH / "atlas_heat.b64").read_text().strip())
out = SCRATCH / "rex-dm3-3d.html"
out.write_text(html)
print(out, f"{out.stat().st_size/1e6:.1f} MB")
