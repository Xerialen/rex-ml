"""Pull dm3's render geometry out of the BSP as triangles, for the replay page.

Quake's BSP29 render lumps are read directly here rather than through `rtx-nav::bsp`, which parses
only the *clip* hulls — the collision model the physics needs. A clip hull is a coarse expanded
volume, not the walls a person recognises, so replaying a run against it would show the bot moving
through a shape that is not the map.

Only positions and face-planes are taken. No textures, no lightmaps: the owner asked for the
movement to be exact and the surfaces to be plain, and a texture-free mesh is also two orders of
magnitude smaller to ship inside one HTML file.

Output is a flat binary blob (little-endian float32 positions, uint32 indices, one normal per
triangle packed as a byte) so the page can hand it straight to WebGL without parsing JSON.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

BSP_VERSION = 29

# lump indices, from Quake's bspfile.h
LUMP_VERTEXES = 3
LUMP_FACES = 7
LUMP_EDGES = 12
LUMP_SURFEDGES = 13
LUMP_TEXINFO = 6
LUMP_TEXTURES = 2


@dataclass
class Lump:
    offset: int
    length: int


def _lumps(data: bytes) -> list[Lump]:
    version = struct.unpack_from("<i", data, 0)[0]
    if version != BSP_VERSION:
        raise ValueError(f"expected BSP version {BSP_VERSION}, got {version}")
    return [Lump(*struct.unpack_from("<ii", data, 4 + 8 * i)) for i in range(15)]


def _texture_names(data: bytes, lump: Lump) -> list[str]:
    """Miptex names, so surfaces that are not part of the visible world — sky, and the animated
    liquids — can be separated out. They are kept but flagged, because a replay that silently hides
    the water in the dm3 lift shaft is hiding part of the map the bot moves through."""
    if lump.length == 0:
        return []
    count = struct.unpack_from("<i", data, lump.offset)[0]
    names = []
    for i in range(count):
        off = struct.unpack_from("<i", data, lump.offset + 4 + 4 * i)[0]
        if off < 0:
            names.append("")
            continue
        raw = data[lump.offset + off:lump.offset + off + 16]
        names.append(raw.split(b"\0")[0].decode("latin-1").lower())
    return names


def load_triangles(bsp_path: str | Path) -> dict:
    data = Path(bsp_path).read_bytes()
    lumps = _lumps(data)

    lv = lumps[LUMP_VERTEXES]
    verts = [struct.unpack_from("<fff", data, lv.offset + 12 * i) for i in range(lv.length // 12)]

    le = lumps[LUMP_EDGES]
    edges = [struct.unpack_from("<HH", data, le.offset + 4 * i) for i in range(le.length // 4)]

    ls = lumps[LUMP_SURFEDGES]
    surfedges = [struct.unpack_from("<i", data, ls.offset + 4 * i)[0] for i in range(ls.length // 4)]

    lt = lumps[LUMP_TEXINFO]
    # texinfo is 40 bytes: 8 floats (two texture vectors) + miptex index + flags
    texinfo = [struct.unpack_from("<i", data, lt.offset + 40 * i + 32)[0] for i in range(lt.length // 40)]
    names = _texture_names(data, lumps[LUMP_TEXTURES])

    lf = lumps[LUMP_FACES]
    # face is 20 bytes: plane(u16) side(u16) firstedge(i32) numedges(u16) texinfo(u16)
    #                   styles(4 bytes) lightofs(i32)
    n_faces = lf.length // 20
    positions: list[float] = []
    indices: list[int] = []
    kinds: list[int] = []  # per triangle: 0 world, 1 sky, 2 liquid

    for f in range(n_faces):
        base = lf.offset + 20 * f
        first_edge, num_edges, ti = struct.unpack_from("<ihh", data, base + 4)
        if num_edges < 3:
            continue
        name = names[texinfo[ti]] if 0 <= ti < len(texinfo) and texinfo[ti] < len(names) else ""
        kind = 1 if name.startswith("sky") else (2 if name.startswith(("*", "!")) else 0)

        ring = []
        for e in range(num_edges):
            se = surfedges[first_edge + e]
            ring.append(edges[se][0] if se >= 0 else edges[-se][1])

        # A BSP face is a convex polygon, so a triangle fan from its first vertex is exact — no
        # tessellation library and no risk of a concave-polygon artefact.
        v0 = len(positions) // 3
        for vi in ring:
            positions.extend(verts[vi])
        for e in range(1, num_edges - 1):
            indices.extend((v0, v0 + e, v0 + e + 1))
            kinds.append(kind)

    return {"positions": positions, "indices": indices, "tri_kinds": kinds,
            "n_faces": n_faces, "n_tris": len(kinds), "n_verts": len(positions) // 3}


def pack(geo: dict) -> bytes:
    """positions f32[3n] | indices u32[3m] | tri_kinds u8[m], with a small header."""
    n_v = len(geo["positions"]) // 3
    n_t = len(geo["tri_kinds"])
    head = struct.pack("<II", n_v, n_t)
    pos = struct.pack(f"<{n_v * 3}f", *geo["positions"])
    idx = struct.pack(f"<{n_t * 3}I", *geo["indices"])
    knd = struct.pack(f"<{n_t}B", *geo["tri_kinds"])
    return head + pos + idx + knd


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "/home/benjamin-adm/rex-ml/rtx/playground/qw/maps/dm3.bsp"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "/home/benjamin-adm/rex-ml/pipeline/out/replay/dm3_geo.bin")
    g = load_triangles(src)
    out.parent.mkdir(parents=True, exist_ok=True)
    blob = pack(g)
    out.write_bytes(blob)
    print(f"faces {g['n_faces']}  triangles {g['n_tris']}  vertices {g['n_verts']}  "
          f"blob {len(blob) / 1e6:.2f} MB -> {out}")
